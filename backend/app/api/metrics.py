from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.metrics import summarize

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("")
def get_metrics(days: int = Query(7, ge=1, le=90), db: Session = Depends(get_db)):
    """最近 N 天的 LLM 调用指标：成功率、耗时 P50/P95、token 用量、估算成本。"""
    return summarize(db, since=datetime.utcnow() - timedelta(days=days))
