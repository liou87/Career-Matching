"""
离线评测指标。全部是纯函数，不调 LLM（编造率的 LLM 判断在 judge.py），
单元测试见 tests/test_eval_metrics.py。
"""
import re
import statistics
import unicodedata
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


_SHORT_ASCII = re.compile(r"[a-z0-9+#.]{1,4}")


def _fold(text: str) -> str:
    return unicodedata.normalize("NFKC", text).lower()


def alias_hit(alias: str, text: str) -> bool:
    """别名是否出现在文本里。不区分大小写和全半角，忽略空白：
    「多模态模型 (VLM)」和「多模态模型(vlm)」视为相同。
    不超过 4 个字符的英文短词要求前后不连着字母数字，避免 Java 命中 JavaScript、Go 命中 Google。
    """
    a = re.sub(r"\s+", "", _fold(alias))
    if not a:
        return False
    if _SHORT_ASCII.fullmatch(a):
        return re.search(rf"(?<![a-z0-9]){re.escape(a)}(?![a-z0-9])", _fold(text)) is not None
    return a in re.sub(r"\s+", "", _fold(text))


def gap_matches(result: dict, label: dict) -> tuple[int, int, int, int]:
    """差距识别的命中计数：(识别到的标注数, 标注数, 对的预测数, 预测数)。

    预测是模型给出的 missing_skills（自由文本），标注是人工确认的缺失技能及其别名
    （别名由 evals/aliases.py 按规则派生，人工校对）。
    一条标注被识别到：任意别名出现在任意一条预测里（匹配规则见 alias_hit）。
    一条预测是对的：它包含任意一条标注的任意别名。
    """
    predicted = result.get("missing_skills") or []
    gold = [m["aliases"] for m in label["missing"]]

    def hits(text: str, aliases: list[str]) -> bool:
        return any(alias_hit(a, text) for a in aliases)

    found = sum(any(hits(p, aliases) for p in predicted) for aliases in gold)
    correct = sum(any(hits(p, aliases) for aliases in gold) for p in predicted)
    return found, len(gold), correct, len(predicted)


def gap_precision_recall(result: dict, label: dict) -> tuple[float | None, float | None]:
    """单次分析的差距识别准确率和召回率，没有预测或没有标注时对应一项为 None。"""
    found, n_gold, correct, n_pred = gap_matches(result, label)
    return (correct / n_pred if n_pred else None), (found / n_gold if n_gold else None)


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

    matches = [gap_matches(r["result"], labels[r["job_id"]]) for r in ok if r["job_id"] in labels]
    precisions = [correct / n_pred for _, _, correct, n_pred in matches if n_pred]
    recalls = [found / n_gold for found, n_gold, _, _ in matches if n_gold]

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
        "gap_labeled_runs": len(matches),
        "gap_precision": _round3(_mean(precisions)),
        # 先算每次分析的召回率再平均：每个岗位权重相同
        "gap_recall": _round3(_mean(recalls)),
        # 所有标注放在一起算：每条差距权重相同，差距多的岗位影响更大
        "gap_recall_micro": _ratio(sum(m[0] for m in matches), sum(m[1] for m in matches)),
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
