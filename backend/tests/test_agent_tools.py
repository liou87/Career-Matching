"""AI 助手的工具：只测确定性的数据查询部分，不调 LLM。"""
import json

from app.agent.job_agent import get_skill_ranking, search_jobs
from app.db import models


def _add(db, title, skills, status="active"):
    db.add(models.Job(raw_jd="原文", title=title, required_skills=skills, status=status))
    db.commit()


def test_search_matches_chinese_skills_and_ignores_case(db):
    _add(db, "大模型工程师", ["大语言模型基本原理", "Python"])
    _add(db, "Agent 工程师", ["LangChain"])

    by_chinese = json.loads(search_jobs.invoke({"keyword": "大语言模型"}))
    by_lowercase = json.loads(search_jobs.invoke({"keyword": "langchain"}))

    assert [j["title"] for j in by_chinese] == ["大模型工程师"]
    assert [j["title"] for j in by_lowercase] == ["Agent 工程师"]


def test_search_skips_archived_jobs(db):
    _add(db, "已删除的 RAG 岗", ["RAG"], status="archived")

    assert json.loads(search_jobs.invoke({"keyword": "RAG"})) == []


def test_skill_ranking_without_batch_returns_hint():
    assert "还没有技能缺口分析结果" in get_skill_ranking.invoke({})
