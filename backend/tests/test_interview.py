"""面试题生成：依赖匹配分析、缓存复用、强制重新生成、AI 助手里需要确认。"""
import pytest

from app.agent.agent import CONFIRM_TOOLS
from app.db import models
from app.llm.schemas import InterviewPrep, InterviewQuestion
from app.services import interview
from tests.fakes import FakeChain

PROFILE = {"name": "测试", "skills": ["Python"]}


def _prep(n=6):
    return InterviewPrep(questions=[
        InterviewQuestion(jd_requirement="RAG", question=f"讲讲 RAG 的召回优化 {i}", category="技术深度",
                          relation="gap" if i % 2 else "strength", answer_points=["要点一", "要点二"])
        for i in range(n)
    ])


@pytest.fixture
def fake_chain(monkeypatch):
    chain = FakeChain(_prep())
    monkeypatch.setattr(interview, "interview_chain", lambda: chain)
    return chain


def _job_with_analysis(client, db):
    client.put("/api/profile", json=PROFILE)
    job = models.Job(raw_jd="", title="Agent 工程师", required_skills=["RAG"], status="active")
    db.add(job)
    db.commit()
    db.add(models.Analysis(job_id=job.id, match_score=60, content_hash="x", summary="",
                           strengths=["会 Python"], gaps=[{"gap": "缺 RAG"}]))
    db.commit()
    return job.id


def test_requires_analysis_first(client, db, fake_chain):
    client.put("/api/profile", json=PROFILE)
    job = models.Job(raw_jd="", title="A", status="active")
    db.add(job)
    db.commit()

    r = client.post(f"/api/interview/{job.id}")

    assert r.status_code == 400 and "匹配分析" in r.json()["detail"]
    assert fake_chain.calls == []


def test_generate_cache_and_force(client, db, fake_chain):
    job_id = _job_with_analysis(client, db)

    first = client.post(f"/api/interview/{job_id}").json()
    again = client.post(f"/api/interview/{job_id}").json()
    forced = client.post(f"/api/interview/{job_id}", params={"force": True}).json()

    assert len(first["questions"]) == 6
    assert first["id"] == again["id"] and len(fake_chain.calls) == 2   # 第二次复用
    assert forced["id"] != first["id"]
    assert client.get(f"/api/interview/{job_id}/latest").json()["id"] == forced["id"]
    # 生成时参考了分析结论
    assert "缺 RAG" in fake_chain.calls[0]["gaps"]


def test_agent_needs_confirmation_to_generate():
    assert "generate_interview_questions" in CONFIRM_TOOLS
