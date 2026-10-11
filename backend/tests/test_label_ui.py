"""差距标注界面的保存逻辑（evals/label_ui.py）。"""
import pytest

from evals.label_ui import apply_label


def test_apply_label_cleans_and_marks_reviewed():
    labels = [{"job_id": 1, "reviewed": False, "missing": [{"skill": "旧", "aliases": ["旧"]}]}]

    entry = apply_label(labels, 1, [
        {"skill": " RAG ", "aliases": ["检索增强", " rag ", ""]},
        {"skill": "rag", "aliases": []},          # 与上一条重复
        {"skill": "  ", "aliases": ["空"]},        # 空技能丢弃
    ], reviewed=True)

    assert entry is labels[0] and entry["reviewed"] is True
    assert entry["missing"] == [{"skill": "RAG", "aliases": ["RAG", "检索增强"]}]


def test_apply_label_unknown_job():
    with pytest.raises(KeyError):
        apply_label([], 99, [], reviewed=True)
