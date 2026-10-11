"""离线评测的指标函数（evals/metrics.py），都是纯函数。"""
import pytest

from evals.aliases import derive_aliases
from evals.judge import suggestion_texts
from evals.metrics import (
    alias_hit,
    gap_precision_recall,
    generic_action_count,
    score_mismatch,
    stability,
    summarize_version,
)

LABEL = {"missing": [
    {"skill": "RAG", "aliases": ["RAG", "检索增强"]},
    {"skill": "Kubernetes", "aliases": ["Kubernetes", "K8s"]},
]}


def test_gap_precision_recall_matches_aliases_case_insensitively():
    result = {"missing_skills": ["缺少检索增强生成经验", "不熟悉 k8s 部署", "缺少 Go 语言"]}

    precision, recall = gap_precision_recall(result, LABEL)

    assert recall == 1.0           # 两条标注都被识别到
    assert precision == pytest.approx(2 / 3)  # 「Go 语言」不在标注里


def test_alias_hit_ignores_spacing_and_width_but_respects_short_words():
    assert alias_hit("多模态模型(VLM)项目经验", "多模态模型 （VLM） 项目经验")
    assert alias_hit("ToB SaaS", "ToB SaaS / 用研调研行业实习经验")
    assert alias_hit("Java", "Java/Spring 后端")
    assert not alias_hit("Java", "JavaScript")
    assert not alias_hit("Go", "Google ADK")
    assert alias_hit("Go", "Python 和 Go 语言")


def test_derive_aliases_splits_alternatives_and_strips_suffixes():
    assert derive_aliases("Solr项目经验") == ["Solr项目经验", "Solr"]
    assert derive_aliases("Terraform或CloudFormation") == ["Terraform或CloudFormation", "Terraform", "CloudFormation"]
    assert derive_aliases("Infrastructure as Code (IaC)") == [
        "Infrastructure as Code (IaC)", "IaC", "Infrastructure as Code",
    ]
    assert derive_aliases("Go") == ["Go", "Golang"]
    assert derive_aliases("参与开源项目") == ["参与开源项目"]


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


def test_gap_recall_per_job_vs_per_label():
    def rec(job_id, missing):
        return {"job_id": job_id, "ok": True, "latency_ms": 1, "cost_usd": None,
                "usage": {"input_tokens": 0, "output_tokens": 0},
                "result": {"match_score": 70, "missing_skills": missing}}

    labels = {
        1: {"missing": [{"skill": "RAG", "aliases": ["RAG"]}]},
        2: {"missing": [{"skill": s, "aliases": [s]} for s in ("Kafka", "Redis", "Docker")]},
    }
    s = summarize_version([rec(1, ["RAG"]), rec(2, [])], labels, [])

    assert s["gap_recall"] == 0.5          # 岗位 1 全对、岗位 2 全漏，两个岗位平均
    assert s["gap_recall_micro"] == 0.25   # 4 条标注只识别到 1 条


def test_judge_checks_actions_and_gap_suggestions():
    result = {
        "action_items": [{"item": "做 X", "why_valuable": "因为 Y", "resource": None}],
        "gaps": [{"gap": "g1", "suggestion": "结合项目 A"}, {"gap": "g2", "suggestion": ""}],
    }
    assert suggestion_texts(result) == ["做 X / 因为 Y", "结合项目 A"]


def test_summarize_version_reports_gap_judgements():
    gap_verdicts = [{"category": "valid"}] * 6 + [{"category": "not_required"}] * 3 + [{"category": "already_has"}]

    s = summarize_version([], {}, [], gap_verdicts)

    assert (s["gap_valid_rate"], s["gap_not_required_rate"], s["gap_already_has_rate"]) == (0.6, 0.3, 0.1)
    assert summarize_version([], {}, [])["gap_valid_rate"] is None


def test_judge_gaps_rejects_incomplete_verdicts(monkeypatch):
    from evals import judge as judge_mod
    from tests.fakes import FakeChain

    partial = judge_mod.GapJudgeResult(
        verdicts=[judge_mod.GapVerdict(index=0, jd_source="RAG", category="valid", evidence="-")]
    )
    monkeypatch.setattr(judge_mod, "gap_judge_chain", lambda: FakeChain(partial))

    with pytest.raises(ValueError, match="对不上"):
        judge_mod.judge_gaps({}, {}, {"missing_skills": ["RAG", "K8s"]})


def test_judge_gaps_corrects_self_contradicting_verdicts(monkeypatch):
    from evals import judge as judge_mod
    from tests.fakes import FakeChain

    verdicts = judge_mod.GapJudgeResult(verdicts=[
        # 摘录到了 JD 原文却判「JD 没要求」，自相矛盾，按 valid 计
        judge_mod.GapVerdict(index=0, jd_source="Text2SQL", category="not_required", evidence="只是加分项"),
        judge_mod.GapVerdict(index=1, jd_source="无", category="not_required", evidence="JD 没提"),
    ])
    monkeypatch.setattr(judge_mod, "gap_judge_chain", lambda: FakeChain(verdicts))

    out = judge_mod.judge_gaps({}, {}, {"missing_skills": ["Text2SQL", "Kafka"]})

    assert [(v["category"], v.get("corrected", False)) for v in out] == [("valid", True), ("not_required", False)]

