"""技能缺口聚合：映射校验和统计逻辑。LLM 用假链代替。"""
import pytest

from app.llm.schemas import SkillMapping, SkillMergeResult
from app.services import aggregate
from tests.fakes import FakeChain

BATCH_RESULTS = [
    {"job_id": 1, "missing_skills": ["缺 RAG 经验", "不熟悉 LangGraph"]},
    {"job_id": 2, "missing_skills": ["没做过检索增强"]},
    {"job_id": 3, "error": "超时"},  # 失败的岗位要被跳过
]


def _install_mapping(monkeypatch, pairs):
    result = SkillMergeResult(mappings=[SkillMapping(index=i, canonical=c) for i, c in pairs])
    monkeypatch.setattr(aggregate, "merge_chain", lambda: FakeChain(result))


def test_ranks_by_number_of_jobs(monkeypatch):
    _install_mapping(monkeypatch, [(0, "RAG"), (1, "LangChain/LangGraph"), (2, "RAG")])

    ranking = aggregate.aggregate_gaps(BATCH_RESULTS)

    assert [r["skill"] for r in ranking] == ["RAG", "LangChain/LangGraph"]
    assert ranking[0]["job_count"] == 2
    assert ranking[0]["originals"] == ["缺 RAG 经验", "没做过检索增强"]
    assert ranking[0]["category"] == "框架工具"  # 从词表反查，不由 LLM 决定


def test_unknown_skill_falls_into_other_category(monkeypatch):
    _install_mapping(monkeypatch, [(0, "RAG"), (1, "其他:某冷门框架"), (2, "RAG")])

    ranking = aggregate.aggregate_gaps(BATCH_RESULTS)

    assert {r["skill"]: r["category"] for r in ranking}["其他:某冷门框架"] == "其他"


@pytest.mark.parametrize(
    ("pairs", "message"),
    [
        ([(0, "RAG"), (1, "RAG")], "数量不一致"),
        ([(0, "RAG"), (0, "RAG"), (2, "RAG")], "重复的 index"),
        ([(0, "RAG"), (1, "RAG"), (9, "RAG")], "越界的 index"),
    ],
)
def test_rejects_broken_mappings(monkeypatch, pairs, message):
    _install_mapping(monkeypatch, pairs)

    with pytest.raises(ValueError, match=message):
        aggregate.aggregate_gaps(BATCH_RESULTS)
