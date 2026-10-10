import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas
from app.core.config import settings
from app.core.errors import classify
from app.core.guard import ai_guard
from app.db import models
from app.db.session import SessionLocal, get_db
from app.graphs.batch import analyze_all
from app.services.aggregate import aggregate_gaps
from app.services.analysis import analyze_job, job_to_dict, profile_to_dict

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/analysis", tags=["analysis"])

BATCH_TIMEOUT = timedelta(minutes=settings.batch_timeout_minutes)


# ---------- 批量分析 ----------
# 在请求里同步跑完（15 个岗位实测约 35 秒）。部署在 Vercel 上时，响应返回后
# 进程随时可能被回收，BackgroundTasks 不可靠，所以不放后台。
# 任务记录和轮询接口保留，前端流程不变。
#
# 这三条 /batch... 路由必须写在下面 /{job_id}... 路由前面：FastAPI/Starlette
# 按声明顺序匹配路由，/{job_id} 和 /{job_id}/latest 在路径形状上会先一步
# "吃掉" /batch、/batch/latest 这类请求（把 "batch"/"latest" 当成 job_id
# 尝试转 int，导致 422），写在前面才能保证字面量路径优先匹配。


def run_batch(task_id: int):
    """批量分析实体。自己开 session，任务状态的读写跟请求的 session 互不影响。"""
    db = SessionLocal()
    try:
        task = db.query(models.BatchAnalysis).filter(models.BatchAnalysis.id == task_id).first()
        if not task:
            return

        task.status = "running"
        task.started_at = datetime.utcnow()
        db.commit()

        profile = db.query(models.Profile).first()
        if not profile:
            raise RuntimeError("没有个人画像，无法批量分析")

        jobs = db.query(models.Job).filter(models.Job.status == "active").all()

        profile_dict = profile_to_dict(profile)
        job_items = [{"job_id": j.id, "job": job_to_dict(j)} for j in jobs]

        results = analyze_all(profile_dict, job_items)
        ranking = aggregate_gaps(results)

        task.job_count = len(jobs)
        task.success_count = len([r for r in results if "error" not in r])
        task.ranking = ranking
        task.status = "done"
        task.finished_at = datetime.utcnow()
        db.commit()
    except Exception as e:
        logger.exception("batch_failed", extra={"fields": {"task_id": task_id}})
        db.rollback()
        task = db.query(models.BatchAnalysis).filter(models.BatchAnalysis.id == task_id).first()
        if task:
            _, code, message = classify(e)
            task.status = "failed"
            # 业务上主动抛的错误（如没有画像）保留原文，LLM 相关的换成友好提示
            task.error = str(e) if code == "INTERNAL" else message
            task.finished_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


@router.post("/batch", dependencies=[Depends(ai_guard)])
def start_batch_analysis(db: Session = Depends(get_db)):
    # 超时的 running 任务（进程被中途回收）不算数，否则会一直挡住新任务
    existing = (
        db.query(models.BatchAnalysis)
        .filter(models.BatchAnalysis.status.in_(["pending", "running"]))
        .filter(models.BatchAnalysis.created_at > datetime.utcnow() - BATCH_TIMEOUT)
        .order_by(models.BatchAnalysis.created_at.desc())
        .first()
    )
    if existing:
        return {"task_id": existing.id}

    task = models.BatchAnalysis(status="pending")
    db.add(task)
    db.commit()
    db.refresh(task)

    run_batch(task.id)
    return {"task_id": task.id}


@router.get("/batch/latest")
def get_latest_batch(db: Session = Depends(get_db)):
    task = (
        db.query(models.BatchAnalysis)
        .filter(models.BatchAnalysis.status == "done")
        .order_by(models.BatchAnalysis.created_at.desc())
        .first()
    )
    if not task:
        return {"status": "none"}
    return schemas.BatchAnalysisOut.model_validate(task)


@router.get("/batch/{task_id}", response_model=schemas.BatchAnalysisOut)
def get_batch_status(task_id: int, db: Session = Depends(get_db)):
    task = db.query(models.BatchAnalysis).filter(models.BatchAnalysis.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Batch task not found")

    if task.status == "running" and task.started_at and datetime.utcnow() - task.started_at > BATCH_TIMEOUT:
        task.status = "failed"
        task.error = "任务超时或进程中断"
        task.finished_at = datetime.utcnow()
        db.commit()
        db.refresh(task)

    return task


# ---------- 单个岗位分析 ----------

@router.post("/{job_id}", response_model=schemas.AnalysisOut, dependencies=[Depends(ai_guard)])
def run_analysis(job_id: int, force: bool = False, db: Session = Depends(get_db)):
    return analyze_job(db, job_id, force=force)


@router.get("/{job_id}/latest", response_model=schemas.AnalysisOut)
def get_latest_analysis(job_id: int, db: Session = Depends(get_db)):
    analysis = (
        db.query(models.Analysis)
        .filter(models.Analysis.job_id == job_id)
        .order_by(models.Analysis.created_at.desc())
        .first()
    )
    if not analysis:
        raise HTTPException(status_code=404, detail="尚未分析此岗位")
    return analysis
