"""AI 助手的读工具：只测确定性的数据查询部分，不调 LLM。"""
import json

from app.agent.tools import get_skill_ranking, list_job_scores, search_jobs
from app.db import models
from app.services.retrieval import index_job


def _add(db, title, skills, status="active", city=None, company=None):
    job = models.Job(raw_jd="原文", title=title, required_skills=skills, status=status, city=city, company=company)
    db.add(job)
    db.commit()
    index_job(db, job)
    return job.id


def _search(**kwargs) -> dict:
    return json.loads(search_jobs.invoke(kwargs))


def test_search_matches_chinese_skills_and_ignores_case(db):
    _add(db, "大模型工程师", ["大语言模型基本原理", "Python"])
    _add(db, "Agent 工程师", ["LangChain"])

    assert [j["title"] for j in _search(query="大语言模型")["results"]] == ["大模型工程师"]
    assert [j["title"] for j in _search(query="langchain")["results"]] == ["Agent 工程师"]


def test_search_returns_matching_snippets(db):
    _add(db, "Agent 工程师", ["LangChain", "RAG"])

    result = _search(query="RAG")["results"][0]

    assert any("RAG" in s for s in result["snippets"])


def test_search_skips_archived_jobs(db):
    _add(db, "已删除的 RAG 岗", ["RAG"], status="archived")

    assert _search(query="RAG") == {"total": 0, "mode": "keyword", "results": []}


def test_search_filters_by_city_and_reports_total(db):
    _add(db, "A", ["Python"], city="深圳")
    _add(db, "B", ["Python"], city="上海")
    _add(db, "C", ["Python"], city="深圳,广州")

    by_city = _search(city="深圳")
    everything = _search()

    assert by_city["total"] == 2 and [j["title"] for j in by_city["results"]] == ["A", "C"]
    assert everything["total"] == 3


def test_list_job_scores_sorted_with_unanalysed_last(db):
    a, b, c = (_add(db, t, ["Python"]) for t in ("A", "B", "C"))
    db.add_all([models.Analysis(job_id=a, match_score=60, content_hash="x", summary=""),
                models.Analysis(job_id=b, match_score=80, content_hash="x", summary="")])
    db.commit()

    rows = json.loads(list_job_scores.invoke({}))["jobs"]

    assert [(r["id"], r["match_score"]) for r in rows] == [(b, 80), (a, 60), (c, None)]


def test_skill_ranking_without_batch_returns_hint():
    assert "还没有技能缺口分析结果" in get_skill_ranking.invoke({})
