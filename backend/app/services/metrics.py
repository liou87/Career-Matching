"""
线上指标：从 llm_calls 表统计成功率、耗时分位数、token 用量和成本。
数据量是个人项目级别（每天几十到几百条），直接在 Python 里算，
不依赖数据库特有的分位数函数，SQLite 和 Postgres 结果一致。
"""
import math
from collections import defaultdict
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import LLMCall


def percentile(values: list[float], p: float) -> float | None:
    """线性插值分位数，p 取 0-100。"""
    if not values:
        return None
    ordered = sorted(values)
    k = (len(ordered) - 1) * p / 100
    lo, hi = math.floor(k), math.ceil(k)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def estimate_cost(model: str, input_tokens: int | None, cached_input_tokens: int | None,
                  output_tokens: int | None) -> float | None:
    """按 settings.model_prices 估算一次调用的美元成本，价格表里没有的模型返回 None。"""
    price = settings.model_prices.get(model)
    if price is None or input_tokens is None or output_tokens is None:
        return None
    cached = cached_input_tokens or 0
    return (
        (input_tokens - cached) * price["input"]
        + cached * price["cached_input"]
        + output_tokens * price["output"]
    ) / 1_000_000


def _summarize_calls(calls: list[LLMCall]) -> dict:
    ok = [c for c in calls if c.ok]
    latencies = [c.latency_ms for c in ok if c.latency_ms is not None]
    costs = [estimate_cost(c.model, c.input_tokens, c.cached_input_tokens, c.output_tokens) for c in ok]
    known_costs = [c for c in costs if c is not None]
    return {
        "calls": len(calls),
        "success_rate": round(len(ok) / len(calls), 4) if calls else None,
        "latency_ms_p50": _round(percentile(latencies, 50)),
        "latency_ms_p95": _round(percentile(latencies, 95)),
        "avg_input_tokens": _round(_mean([c.input_tokens for c in ok if c.input_tokens is not None])),
        "avg_output_tokens": _round(_mean([c.output_tokens for c in ok if c.output_tokens is not None])),
        "cost_usd": round(sum(known_costs), 6) if known_costs else None,
    }


def summarize(db: Session, since: datetime) -> dict:
    calls = db.query(LLMCall).filter(LLMCall.created_at >= since).all()

    by_role = defaultdict(list)
    for c in calls:
        by_role[c.role].append(c)

    # 一次匹配分析 = 1 次 analysis + 0 或 1 次 suggest（技术栈不符的岗位跳过建议）。
    # 按「analysis + suggest 的总成本 / 成功的 analysis 次数」算平均单次成本，
    # 批量分析里的每个岗位也按一次分析计
    analyses = [c for c in by_role.get("analysis", []) if c.ok]
    pair_costs = [
        estimate_cost(c.model, c.input_tokens, c.cached_input_tokens, c.output_tokens)
        for c in by_role.get("analysis", []) + by_role.get("suggest", []) if c.ok
    ]
    cost_per_analysis = (
        round(sum(x for x in pair_costs if x is not None) / len(analyses), 6)
        if analyses and all(x is not None for x in pair_costs) else None
    )

    return {
        "since": since.isoformat(),
        "overall": _summarize_calls(calls),
        "by_role": {role: _summarize_calls(items) for role, items in sorted(by_role.items())},
        "analysis": {"count": len(analyses), "avg_cost_usd": cost_per_analysis},
    }


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _round(x: float | None) -> float | None:
    return None if x is None else round(x, 1)
