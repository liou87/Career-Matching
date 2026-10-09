"""岗位入库：接口层和 AI 助手的 add_job 工具共用。"""
from sqlalchemy.orm import Session

from app.db import models
from app.services.jd_parser import parse_jd


def create_job(db: Session, raw_jd: str, source_url: str | None = None) -> models.Job:
    """解析 JD 原文并入库。"""
    job = models.Job(raw_jd=raw_jd, source_url=source_url, **parse_jd(raw_jd))
    db.add(job)
    db.commit()
    db.refresh(job)
    return job
