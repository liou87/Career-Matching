"""线上指标：调用记录落库、分位数、成本估算。"""
from datetime import datetime, timedelta

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from app.core.logging import request_id_var
from app.db.models import LLMCall
from app.llm.callbacks import LLMCallLogger
from app.services.metrics import estimate_cost, percentile


def test_percentile_interpolates():
    assert percentile([], 50) is None
    assert percentile([100], 95) == 100
    assert percentile([100, 200, 300, 400], 50) == 250
    assert percentile(list(range(1, 101)), 95) == pytest.approx(95.05)


def test_estimate_cost_separates_cached_input():
    # deepseek-flash：输入 0.30、缓存命中 0.006、输出 1.2（美元 / 百万 token）
    cost = estimate_cost("deepseek-flash", input_tokens=1_000_000, cached_input_tokens=400_000,
                         output_tokens=100_000)
    assert cost == pytest.approx(0.6 * 0.30 + 0.4 * 0.006 + 0.1 * 1.2)
    assert estimate_cost("unknown-model", 100, 0, 100) is None


def test_llm_calls_are_recorded_with_request_id(db):
    reply = AIMessage(content="ok", usage_metadata={
        "input_tokens": 1000, "output_tokens": 200, "total_tokens": 1200,
        "input_token_details": {"cache_read": 300},
    })
    model = GenericFakeChatModel(messages=iter([reply]), callbacks=[LLMCallLogger("analysis", "deepseek-flash")])

    token = request_id_var.set("req-123")
    try:
        model.invoke("hi")
    finally:
        request_id_var.reset(token)

    row = db.query(LLMCall).one()
    assert (row.request_id, row.role, row.ok) == ("req-123", "analysis", True)
    assert (row.input_tokens, row.cached_input_tokens, row.output_tokens) == (1000, 300, 200)


def _add(db, role, ok=True, ms=1000, model="deepseek-flash", inp=1000, out=500, age_days=0):
    db.add(LLMCall(role=role, ok=ok, latency_ms=ms, model=model, input_tokens=inp, cached_input_tokens=0,
                   output_tokens=out, created_at=datetime.utcnow() - timedelta(days=age_days)))


def test_summarize(db, client):
    _add(db, "analysis", ms=3000)
    _add(db, "analysis", ms=5000)
    _add(db, "analysis", ok=False, ms=None, inp=None, out=None)
    _add(db, "suggest", ms=6000)  # 第二次分析是排除岗，没有 suggest
    _add(db, "analysis", age_days=30)  # 超出统计窗口
    db.commit()

    m = client.get("/api/metrics", params={"days": 7}).json()

    analysis = m["by_role"]["analysis"]
    assert analysis["calls"] == 3
    assert analysis["success_rate"] == pytest.approx(2 / 3, abs=1e-4)
    assert analysis["latency_ms_p50"] == 4000
    assert m["overall"]["calls"] == 4
    # 每次调用 1000 输入 + 500 输出 = 0.0009 美元；3 次成功调用 / 2 次成功分析
    assert m["analysis"] == {"count": 2, "avg_cost_usd": pytest.approx(0.0009 * 3 / 2)}
