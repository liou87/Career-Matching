"""
AI 接口的守卫：按 IP 限流 + 全站每日 token 预算。

挂在所有会调用 AI 的接口上（Depends(ai_guard)）。Serverless 下多个实例不共享内存，
计数都放在数据库里：请求次数记在 ai_requests，token 用量直接从 llm_calls 汇总。
"""
from datetime import datetime, timedelta, timezone

from fastapi import Depends, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import BudgetExceededError, RateLimitedError
from app.db import models
from app.db.session import get_db

BEIJING = timezone(timedelta(hours=8))


def client_ip(request: Request) -> str:
    # Vercel 和常见反向代理把真实客户端 IP 放在 X-Forwarded-For 的第一个
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "unknown")


def today_start_utc() -> datetime:
    """北京时间今天零点，换算成 UTC（库里的时间都是不带时区的 UTC）。"""
    start = datetime.now(BEIJING).replace(hour=0, minute=0, second=0, microsecond=0)
    return start.astimezone(timezone.utc).replace(tzinfo=None)


def tokens_used_today(db: Session) -> int:
    used = (
        db.query(func.coalesce(func.sum(models.LLMCall.input_tokens), 0)
                 + func.coalesce(func.sum(models.LLMCall.output_tokens), 0))
        .filter(models.LLMCall.created_at >= today_start_utc())
        .scalar()
    )
    return int(used or 0)


def ai_guard(request: Request, db: Session = Depends(get_db)) -> None:
    ip = client_ip(request)

    if settings.ai_rate_limit:
        since = datetime.utcnow() - timedelta(minutes=settings.ai_rate_window_minutes)
        recent = (
            db.query(models.AIRequest)
            .filter(models.AIRequest.client_ip == ip, models.AIRequest.created_at >= since)
            .count()
        )
        if recent >= settings.ai_rate_limit:
            raise RateLimitedError(f"请求太频繁，请 {settings.ai_rate_window_minutes} 分钟后再试")

    if settings.daily_token_budget and tokens_used_today(db) >= settings.daily_token_budget:
        raise BudgetExceededError("今天的 AI 额度已用完，明天再试")

    db.add(models.AIRequest(client_ip=ip, path=request.url.path))
    db.commit()
