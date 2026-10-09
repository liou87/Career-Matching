"""
匹配分的计算。加权求和只在这里做一次，LLM 只负责给四个子分。
"""
import math

from app.core.config import settings


def clamp_score(value) -> int:
    """把任意输入收敛到 0-100 的整数，无法解析时记 0。"""
    try:
        v = _round_half_up(float(value))
    except (TypeError, ValueError):
        v = 0
    return max(0, min(100, v))


def clamp_breakdown(value) -> dict | None:
    if not isinstance(value, dict):
        return None
    return {k: clamp_score(value.get(k)) for k in settings.score_weights}


def weighted_score(breakdown: dict) -> int:
    exact = sum(breakdown[k] * w for k, w in settings.score_weights.items())
    return clamp_score(exact)


def _round_half_up(x: float) -> int:
    # 不用 round()：Python 的 round 是银行家舍入（72.5 -> 72）。
    # 先 round 到 6 位小数，消掉 0.3*70 = 21.000000000000004 这类浮点误差
    return math.floor(round(x, 6) + 0.5)
