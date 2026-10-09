"""
离线评测指标。全部是纯函数，不调 LLM（编造率的 LLM 判断在 judge.py），
单元测试见 tests/test_eval_metrics.py。
"""
import statistics
from collections import defaultdict

from app.services.metrics import percentile
from app.services.scoring import weighted_score

# action item 命中这些短语视为空泛建议，与 SUGGESTION_PROMPT 明确禁止的措辞对应，
# 也与 v1→v3 历史评测（evals/*_eval.py）的口径一致
GENERIC_PHRASES = ["系统学习", "学习LangChain", "争取实习", "开源到GitHub", "刷LeetCode"]


def score_mismatch(result: dict) -> bool:
    """match_score 与按子分加权算出的值不一致（v1 由 LLM 自己算加权，最容易出错）。"""
    breakdown = result.get("score_breakdown")
    if not breakdown:
        return False
    return result["match_score"] != weighted_score(breakdown)


def generic_action_count(result: dict) -> int:
    return sum(
        any(p in a.get("item", "") for p in GENERIC_PHRASES)
        for a in result.get("action_items") or []
    )


def gap_precision_recall(result: dict, label: dict) -> tuple[float | None, float | None]:
    """差距识别的准确率和召回率。

    预测是模型给出的 missing_skills（自由文本），标注是人工确认的缺失技能及其别名。
    一条标注被识别到：任意别名出现在任意一条预测里（不区分大小写）。
    一条预测是对的：它包含任意一条标注的任意别名。
    """
    predicted = [p.lower() for p in result.get("missing_skills") or []]
    gold = [[a.lower() for a in m["aliases"]] for m in label["missing"]]

    def hits(text: str, aliases: list[str]) -> bool:
        return any(a in text for a in aliases)

    recall = (
        sum(any(hits(p, aliases) for p in predicted) for aliases in gold) / len(gold)
        if gold else None
    )
    precision = (
        sum(any(hits(p, aliases) for aliases in gold) for p in predicted) / len(predicted)
        if predicted else None
    )
    return precision, recall


def stability(records: list[dict]) -> dict:
    """同一岗位多次运行的分数波动：每个岗位算一次标准差和极差，再汇总。"""
    scores = defaultdict(list)
    for r in records:
        if r["ok"]:
            scores[r["job_id"]].append(r["result"]["match_score"])
    multi = {job: s for job, s in scores.items() if len(s) >= 2}
    if not multi:
        return {"jobs": 0, "mean_std": None, "max_range": None, "identical_ratio": None}
    return {
        "jobs": len(multi),
        "mean_std": round(statistics.mean(statistics.pstdev(s) for s in multi.values()), 2),
        "max_range": max(max(s) - min(s) for s in multi.values()),
        "identical_ratio": round(sum(len(set(s)) == 1 for s in multi.values()) / len(multi), 3),
    }


def summarize_version(records: list[dict], labels: dict[int, dict], verdicts: list[dict],
                      gap_verdicts: list[dict] = ()) -> dict:
    """汇总一个版本的全部记录。verdicts、gap_verdicts 是裁判的判断（可以为空）。"""
    ok = [r for r in records if r["ok"]]
    latencies = [r["latency_ms"] for r in ok]
    costs = [r["cost_usd"] for r in ok if r["cost_usd"] is not None]
    actions = [a for r in ok for a in r["result"].get("action_items") or []]

    prs = [gap_precision_recall(r["result"], labels[r["job_id"]]) for r in ok if r["job_id"] in labels]
    precisions = [p for p, _ in prs if p is not None]
    recalls = [rc for _, rc in prs if rc is not None]

    fabricated = [v for v in verdicts if v["fabricated"]]
    gap_counts = {c: sum(v["category"] == c for v in gap_verdicts) for c in ("valid", "not_required", "already_has")}

    return {
        "runs": len(records),
        "success_rate": round(len(ok) / len(records), 3) if records else None,
        "latency_ms_p50": _round(percentile(latencies, 50)),
        "latency_ms_p95": _round(percentile(latencies, 95)),
        "avg_input_tokens": _round(_mean([r["usage"]["input_tokens"] for r in ok])),
        "avg_output_tokens": _round(_mean([r["usage"]["output_tokens"] for r in ok])),
        "avg_cost_usd": round(_mean(costs), 5) if costs else None,
        "score_mismatch": sum(score_mismatch(r["result"]) for r in ok),
        "action_items": len(actions),
        "generic_actions": sum(generic_action_count(r["result"]) for r in ok),
        "stability": stability(records),
        "gap_labeled_runs": len(prs),
        "gap_precision": _round3(_mean(precisions)),
        "gap_recall": _round3(_mean(recalls)),
        "gap_judged": len(gap_verdicts),
        "gap_valid_rate": _ratio(gap_counts["valid"], len(gap_verdicts)),
        "gap_not_required_rate": _ratio(gap_counts["not_required"], len(gap_verdicts)),
        "gap_already_has_rate": _ratio(gap_counts["already_has"], len(gap_verdicts)),
        "judged_items": len(verdicts),
        "fabrication_rate": round(len(fabricated) / len(verdicts), 3) if verdicts else None,
    }


def _mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def _ratio(part, total):
    return round(part / total, 3) if total else None


def _round(x):
    return None if x is None else round(x, 1)


def _round3(x):
    return None if x is None else round(x, 3)
