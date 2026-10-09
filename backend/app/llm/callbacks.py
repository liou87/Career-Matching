"""
LLM 调用日志：每次调用记录角色、模型、耗时、token 用量和成败，
同时写一行日志和一条 llm_calls 记录。这是线上指标（成功率、耗时分位数、
单次成本）的数据来源。
"""
import logging
import time
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from app.core.config import settings
from app.core.logging import request_id_var
from app.db.models import LLMCall
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


class LLMCallLogger(BaseCallbackHandler):
    def __init__(self, role: str, model: str):
        self.role = role
        self.model = model
        self._started: dict[UUID, float] = {}

    def on_chat_model_start(self, serialized, messages, *, run_id: UUID, **kwargs) -> None:
        self._started[run_id] = time.perf_counter()

    def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs) -> None:
        fields = self._base_fields(run_id)
        usage = _usage(response)
        if usage:
            fields.update(
                input_tokens=usage.get("input_tokens"),
                cached_input_tokens=(usage.get("input_token_details") or {}).get("cache_read"),
                output_tokens=usage.get("output_tokens"),
            )
        fields["ok"] = True
        logger.info("llm_call", extra={"fields": fields})
        _record(fields)

    def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs) -> None:
        fields = self._base_fields(run_id)
        fields["error"] = f"{type(error).__name__}: {error}"
        fields["ok"] = False
        logger.warning("llm_call", extra={"fields": fields})
        _record(fields)

    def _base_fields(self, run_id: UUID) -> dict:
        started = self._started.pop(run_id, None)
        ms = round((time.perf_counter() - started) * 1000) if started else None
        return {"role": self.role, "model": self.model, "ms": ms}


def _usage(response: LLMResult) -> dict | None:
    try:
        return response.generations[0][0].message.usage_metadata
    except (IndexError, AttributeError):
        return None


def _record(fields: dict) -> None:
    """写一条调用记录。失败只记警告：指标丢一条可以接受，不能因此让请求失败。"""
    if not settings.record_llm_calls:
        return
    request_id = request_id_var.get()
    try:
        with SessionLocal() as db:
            db.add(LLMCall(
                request_id=None if request_id == "-" else request_id,
                role=fields["role"],
                model=fields["model"],
                ok=fields["ok"],
                latency_ms=fields["ms"],
                input_tokens=fields.get("input_tokens"),
                cached_input_tokens=fields.get("cached_input_tokens"),
                output_tokens=fields.get("output_tokens"),
                error=(fields.get("error") or "")[:300] or None,
            ))
            db.commit()
    except Exception:
        logger.warning("llm_call_record_failed", exc_info=True)
