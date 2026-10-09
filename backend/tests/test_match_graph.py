"""匹配分析状态图：路由、重试和分数计算。LLM 用假链代替。"""
import pytest

from app.core.errors import LLMOutputError
from app.graphs.match import analyze_match_v3
from app.llm import chains
from tests.fakes import FakeChain, make_analysis, make_suggestion

PROFILE = {"name": "测试", "skills": ["Python"]}
JOB = {"title": "AI 工程师", "required_skills": ["Python", "LangGraph"]}


@pytest.fixture
def fake_chains(monkeypatch):
    def install(analysis_outputs, suggestion_outputs=(make_suggestion(),)):
        fa, fs = FakeChain(*analysis_outputs), FakeChain(*suggestion_outputs)
        monkeypatch.setattr(chains, "analysis_chain", lambda: fa)
        monkeypatch.setattr(chains, "suggestion_chain", lambda: fs)
        return fa, fs

    return install


def test_normal_job_goes_through_suggest(fake_chains):
    fa, fs = fake_chains([make_analysis()])

    result = analyze_match_v3(PROFILE, JOB)

    assert len(fa.calls) == 1 and len(fs.calls) == 1
    assert result["match_score"] == 70  # 分数由代码按子分加权，不取 LLM 的
    assert len(result["action_items"]) == 2


def test_excluded_job_skips_suggestion_llm_call(fake_chains):
    fa, fs = fake_chains([make_analysis()])

    result = analyze_match_v3(PROFILE, {**JOB, "required_skills": ["Java", "Spring"]})

    assert len(fs.calls) == 0
    assert result["action_items"] == []
    assert "java" in result["summary"]


def test_empty_llm_output_is_retried(fake_chains):
    fa, _ = fake_chains([None, make_analysis()])

    result = analyze_match_v3(PROFILE, JOB)

    assert len(fa.calls) == 2
    assert result["match_score"] == 70


def test_gives_up_after_three_attempts(fake_chains):
    fa, _ = fake_chains([None])

    with pytest.raises(LLMOutputError):
        analyze_match_v3(PROFILE, JOB)
    assert len(fa.calls) == 3
