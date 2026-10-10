"""AI 接口的限流和每日 token 预算。"""
from datetime import timedelta

import pytest

import app.services.jobs as jobs_service
from app.core.config import settings
from app.core.guard import today_start_utc
from app.db import models


@pytest.fixture(autouse=True)
def fake_parse(monkeypatch):
    monkeypatch.setattr(jobs_service, "parse_jd", lambda raw: {"title": "AI 工程师"})


def _post_job(client, ip="1.1.1.1"):
    return client.post("/api/jobs", json={"raw_jd": "x"}, headers={"X-Forwarded-For": ip})


def test_rate_limit_is_per_ip(client, monkeypatch):
    monkeypatch.setattr(settings, "ai_rate_limit", 2)

    assert [_post_job(client).status_code for _ in range(3)] == [200, 200, 429]
    assert _post_job(client).json()["code"] == "RATE_LIMITED"
    assert _post_job(client, ip="2.2.2.2").status_code == 200   # 另一个 IP 不受影响


def test_daily_token_budget(client, db, monkeypatch):
    monkeypatch.setattr(settings, "daily_token_budget", 1000)
    db.add(models.LLMCall(role="analysis", ok=True, input_tokens=700, output_tokens=400,
                          created_at=today_start_utc() + timedelta(hours=1)))
    db.commit()

    r = _post_job(client)

    assert (r.status_code, r.json()["code"]) == (503, "BUDGET_EXCEEDED")


def test_yesterday_usage_does_not_count(client, db, monkeypatch):
    monkeypatch.setattr(settings, "daily_token_budget", 1000)
    db.add(models.LLMCall(role="analysis", ok=True, input_tokens=5000, output_tokens=0,
                          created_at=today_start_utc() - timedelta(minutes=1)))
    db.commit()

    assert _post_job(client).status_code == 200


def test_limits_can_be_disabled(client, monkeypatch):
    monkeypatch.setattr(settings, "ai_rate_limit", 0)
    monkeypatch.setattr(settings, "daily_token_budget", 0)

    assert all(_post_job(client).status_code == 200 for _ in range(25))


def test_read_endpoints_are_not_limited(client, monkeypatch):
    monkeypatch.setattr(settings, "ai_rate_limit", 1)
    _post_job(client)

    assert client.get("/api/jobs", headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 200
