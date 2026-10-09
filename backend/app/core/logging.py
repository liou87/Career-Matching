"""
结构化日志。

- 每个请求带 request_id，同一请求里的所有日志都能串起来
- 本地输出易读的单行文本；线上设 LOG_JSON=true，每条一行 JSON，方便检索
- 附加字段用 extra={"fields": {...}} 传入
"""
import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone

from app.core.config import settings

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": record.request_id,
            "msg": record.getMessage(),
            **getattr(record, "fields", {}),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class _TextFormatter(logging.Formatter):
    def __init__(self):
        super().__init__("%(asctime)s %(levelname)-7s [%(request_id)s] %(name)s: %(message)s")

    def format(self, record: logging.LogRecord) -> str:
        line = super().format(record)
        fields = getattr(record, "fields", None)
        if fields:
            line += " " + " ".join(f"{k}={v}" for k, v in fields.items())
        return line


def setup_logging() -> None:
    # 只配置 app 这一支 logger，不动 root 和 uvicorn 自己的 logger
    logger = logging.getLogger("app")
    if logger.handlers:  # uvicorn --reload 会重复 import，避免重复挂 handler
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(_RequestIdFilter())
    handler.setFormatter(_JsonFormatter() if settings.log_json else _TextFormatter())
    logger.addHandler(handler)
    logger.setLevel(settings.log_level.upper())
    logger.propagate = False
