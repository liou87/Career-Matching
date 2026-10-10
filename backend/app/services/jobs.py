"""岗位入库：接口层和 AI 助手的 add_job 工具共用。"""
import logging

from sqlalchemy.orm import Session

from app.db import models
from app.services import retrieval
from app.services.jd_parser import parse_jd

logger = logging.getLogger(__name__)


def create_job(db: Session, raw_jd: str, source_url: str | None = None) -> models.Job:
    """解析 JD 原文并入库，同步建检索索引。建索引出问题不影响岗位入库。"""
    job = models.Job(raw_jd=raw_jd, source_url=source_url, **parse_jd(raw_jd))
    db.add(job)
    db.commit()
    db.refresh(job)
    try:
        retrieval.index_job(db, job)
    except Exception:
        db.rollback()
        logger.warning("index_job_failed", exc_info=True, extra={"fields": {"job_id": job.id}})
    return job
