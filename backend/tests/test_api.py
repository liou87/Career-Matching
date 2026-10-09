"""接口层：鉴权、错误响应、分析缓存、批量任务、清单。LLM 相关函数全部替换掉。"""
from urllib.parse import quote

import httpx
import openai
import pytest

import app.api.analysis as analysis_api
import app.services.analysis as analysis_service
import app.services.jobs as jobs_service
from app.core.config import settings
from app.db import models
from tests.fakes import fake_match_result

PROFILE = {"name": "测试用户", "skills": ["Python", "FastAPI"], "target_roles": ["AI 工程师"]}


def _add_job(db, **overrides) -> int:
    job = models.Job(raw_jd="原文", title="AI 工程师", company="某公司",
                     required_skills=["Python"], status="active", **overrides)
    db.add(job)
    db.commit()
    return job.id


# ---------- 鉴权与错误格式 ----------

def test_health_is_public_even_with_token(client, monkeypatch):
    monkeypatch.setattr(settings, "access_token", "口令")
    assert client.get("/api/health").status_code == 200


def test_access_token(client, monkeypatch):
    monkeypatch.setattr(settings, "access_token", "口令")

    denied = client.get("/api/jobs")
    assert denied.status_code == 401
    assert denied.json()["code"] == "UNAUTHORIZED"

    # 前端会对口令做 encodeURIComponent，中文口令也能用
    assert client.get("/api/jobs", headers={"X-Access-Token": quote("口令")}).status_code == 200


def test_error_response_carries_request_id(client, monkeypatch):
    def timeout(_):
        raise openai.APITimeoutError(request=httpx.Request("POST", "https://llm.test"))

    monkeypatch.setattr(jobs_service, "parse_jd", timeout)

    r = client.post("/api/jobs", json={"raw_jd": "x"})

    assert r.status_code == 504
    assert r.json()["code"] == "LLM_TIMEOUT"
    assert r.json()["request_id"] == r.headers["X-Request-ID"]


def test_unexpected_error_does_not_leak_details(client, monkeypatch):
    def boom(_):
        raise KeyError("secret internals")

    monkeypatch.setattr(jobs_service, "parse_jd", boom)

    r = client.post("/api/jobs", json={"raw_jd": "x"})

    assert r.status_code == 500
    assert "secret" not in r.text


# ---------- 岗位 ----------

def test_add_list_and_archive_job(client, monkeypatch):
    monkeypatch.setattr(jobs_service, "parse_jd", lambda raw: {"title": "Agent 工程师", "required_skills": ["LangGraph"]})

    job_id = client.post("/api/jobs", json={"raw_jd": "原文"}).json()["id"]
    assert [j["id"] for j in client.get("/api/jobs").json()] == [job_id]

    client.delete(f"/api/jobs/{job_id}")
    assert client.get("/api/jobs").json() == []
    assert client.get(f"/api/jobs/{job_id}").json()["status"] == "archived"  # 软删除


# ---------- 匹配分析 ----------

@pytest.fixture
def fake_v3(monkeypatch):
    calls = []

    def fake(profile, job):
        calls.append(job)
        return fake_match_result()

    monkeypatch.setattr(analysis_service, "analyze_match_v3", fake)
    return calls


def test_analysis_requires_profile(client, db, fake_v3):
    job_id = _add_job(db)
    assert client.post(f"/api/analysis/{job_id}").status_code == 400


def test_analysis_is_cached_until_inputs_change(client, db, fake_v3):
    client.put("/api/profile", json=PROFILE)
    job_id = _add_job(db)

    first = client.post(f"/api/analysis/{job_id}").json()
    second = client.post(f"/api/analysis/{job_id}").json()
    assert first["id"] == second["id"] and len(fake_v3) == 1  # 画像和岗位都没变，复用结果

    forced = client.post(f"/api/analysis/{job_id}", params={"force": True}).json()
    assert forced["id"] != first["id"] and len(fake_v3) == 2

    client.put("/api/profile", json={**PROFILE, "skills": ["Python", "RAG"]})
    client.post(f"/api/analysis/{job_id}")
    assert len(fake_v3) == 3  # 画像变了，重新分析


def test_analysis_score_is_recomputed_from_breakdown(client, db, fake_v3):
    client.put("/api/profile", json=PROFILE)
    job_id = _add_job(db)

    result = client.post(f"/api/analysis/{job_id}").json()

    # fake 返回的 match_score 是 0，接口层按子分加权得到 70
    assert result["match_score"] == 70


# ---------- 批量分析 ----------

def test_batch_analysis(client, db, monkeypatch):
    client.put("/api/profile", json=PROFILE)
    _add_job(db)
    monkeypatch.setattr(analysis_api, "analyze_all", lambda profile, jobs: [{"job_id": 1, "missing_skills": ["RAG"]}])
    ranking = [{"skill": "RAG", "job_count": 1, "category": "框架工具", "originals": ["RAG"]}]
    monkeypatch.setattr(analysis_api, "aggregate_gaps", lambda results: ranking)

    task_id = client.post("/api/analysis/batch").json()["task_id"]

    task = client.get(f"/api/analysis/batch/{task_id}").json()
    assert task["status"] == "done" and task["success_count"] == 1
    assert client.get("/api/analysis/batch/latest").json()["ranking"][0]["skill"] == "RAG"


def test_batch_failure_stores_readable_reason(client, db, monkeypatch):
    client.put("/api/profile", json=PROFILE)
    _add_job(db)

    def timeout(profile, jobs):
        raise openai.APITimeoutError(request=httpx.Request("POST", "https://llm.test"))

    monkeypatch.setattr(analysis_api, "analyze_all", timeout)

    task_id = client.post("/api/analysis/batch").json()["task_id"]

    task = client.get(f"/api/analysis/batch/{task_id}").json()
    assert task["status"] == "failed"
    assert task["error"] == "AI 服务响应超时，请稍后重试"


# ---------- 清单 ----------

def test_checklist_crud(client):
    items = [
        {"content": "补 RAG 项目", "importance": "高", "category": "gap"},
        {"content": "写评测报告", "importance": "high", "category": "action"},
    ]
    created = client.post("/api/checklist", json={"items": items}).json()
    assert {i["category"] for i in created} == {"gap", "action"}

    item_id = created[0]["id"]
    assert client.patch(f"/api/checklist/{item_id}", json={"status": "done"}).json()["status"] == "done"
    client.delete(f"/api/checklist/{item_id}")
    assert len(client.get("/api/checklist").json()) == 1


def test_insufficient_llm_balance_has_clear_message(client, monkeypatch):
    def no_balance(_):
        raise openai.APIStatusError("Insufficient Balance",
                                    response=httpx.Response(402, request=httpx.Request("POST", "https://llm.test")),
                                    body=None)

    monkeypatch.setattr(jobs_service, "parse_jd", no_balance)

    r = client.post("/api/jobs", json={"raw_jd": "x"})

    assert (r.status_code, r.json()["code"]) == (503, "LLM_QUOTA")

