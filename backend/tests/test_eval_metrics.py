"""离线评测的指标函数（evals/metrics.py），都是纯函数。"""
import pytest

from evals.judge import suggestion_texts
from evals.metrics import gap_precision_recall, generic_action_count, score_mismatch, stability, summarize_version

LABEL = {"missing": [
    {"skill": "RAG", "aliases": ["RAG", "检索增强"]},
    {"skill": "Kubernetes", "aliases": ["Kubernetes", "K8s"]},
]}


def test_gap_precision_recall_matches_aliases_case_insensitively():
    result = {"missing_skills": ["缺少检索增强生成经验", "不熟悉 k8s 部署", "缺少 Go 语言"]}

    precision, recall = gap_precision_recall(result, LABEL)

    assert recall == 1.0           # 两条标注都被识别到
    assert precision == pytest.approx(2 / 3)  # 「Go 语言」不在标注里


def test_gap_precision_recall_handles_empty_lists():
    assert gap_precision_recall({"missing_skills": []}, LABEL) == (None, 0.0)
    assert gap_precision_recall({"missing_skills": ["x"]}, {"missing": []}) == (0.0, None)


def test_score_mismatch_detects_llm_arithmetic_errors():
    breakdown = {"skills": 80, "experience": 70, "education": 60, "other": 50}  # 加权 69.5 -> 70
    assert score_mismatch({"match_score": 70, "score_breakdown": breakdown}) is False
    assert score_mismatch({"match_score": 69, "score_breakdown": breakdown}) is True


def test_generic_action_count():
    result = {"action_items": [{"item": "系统学习 LangGraph"}, {"item": "给匹配流程补评测并给出前后对比数据"}]}
    assert generic_action_count(result) == 1


def _rec(job_id, score, ok=True):
    return {"job_id": job_id, "ok": ok, "result": {"match_score": score} if ok else None}


def test_stability_per_job_then_aggregated():
    records = [_rec(1, 70), _rec(1, 70), _rec(1, 70), _rec(2, 60), _rec(2, 66), _rec(2, 0, ok=False)]

    s = stability(records)

    assert s["jobs"] == 2
    assert s["max_range"] == 6
    assert s["identical_ratio"] == 0.5
    assert s["mean_std"] == 1.5  # 岗位 1 标准差 0，岗位 2 为 3


def test_summarize_version_counts_failures_and_fabrication():
    ok = {"job_id": 1, "ok": True, "run": 0, "latency_ms": 1000, "cost_usd": 0.002,
          "usage": {"input_tokens": 3000, "output_tokens": 1500},
          "result": {"match_score": 70, "score_breakdown": None, "missing_skills": ["RAG"],
                     "action_items": [{"item": "a"}]}}
    failed = {"job_id": 2, "ok": False, "run": 0, "latency_ms": 500, "cost_usd": None,
              "usage": {"input_tokens": 0, "output_tokens": 0}, "result": None}
    verdicts = [{"fabricated": True}, {"fabricated": False}, {"fabricated": False}, {"fabricated": False}]

    s = summarize_version([ok, failed], {1: LABEL}, verdicts)

    assert s["success_rate"] == 0.5
    assert s["latency_ms_p50"] == 1000  # 只统计成功的
    assert s["gap_recall"] == 0.5
    assert s["fabrication_rate"] == 0.25


def test_judge_checks_actions_and_gap_suggestions():
    result = {
        "action_items": [{"item": "做 X", "why_valuable": "因为 Y", "resource": None}],
        "gaps": [{"gap": "g1", "suggestion": "结合项目 A"}, {"gap": "g2", "suggestion": ""}],
    }
    assert suggestion_texts(result) == ["做 X / 因为 Y", "结合项目 A"]
