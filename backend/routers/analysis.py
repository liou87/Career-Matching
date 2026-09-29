import hashlib
import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db, SessionLocal
from services.graph import analyze_match_v3
from services.batch_graph import analyze_all
from services.aggregate import aggregate_gaps
import models, schemas

router = APIRouter(prefix="/analysis", tags=["analysis"])

BATCH_TIMEOUT = timedelta(minutes=5)


def _content_hash(profile: dict, job: dict) -> str:
    payload = json.dumps({"profile": profile, "job": job}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _clamp_score(value) -> int:
    try:
        v = int(round(float(value)))
    except (TypeError, ValueError):
        v = 0
    return max(0, min(100, v))


def _clamp_breakdown(value) -> dict | None:
    if not isinstance(value, dict):
        return None
    return {k: _clamp_score(value.get(k)) for k in ("skills", "experience", "education", "other")}


def _weighted_score(breakdown: dict) -> int:
    return _clamp_score(
        breakdown["skills"] * 0.4
        + breakdown["experience"] * 0.3
        + breakdown["education"] * 0.15
        + breakdown["other"] * 0.15
    )


def _profile_to_dict(profile: models.Profile) -> dict:
    return {
        "name": profile.name,
        "education": profile.education,
        "skills": profile.skills,
        "experiences": profile.experiences,
        "projects": profile.projects,
        "target_roles": profile.target_roles,
        "target_cities": profile.target_cities,
        "target_companies": profile.target_companies,
    }


def _job_to_dict(job: models.Job) -> dict:
    return {
        "title": job.title,
        "company": job.company,
        "city": job.city,
        "salary_min": job.salary_min,
        "salary_max": job.salary_max,
        "required_skills": job.required_skills,
        "preferred_skills": job.preferred_skills,
        "experience_required": job.experience_required,
        "education_required": job.education_required,
        "responsibilities": job.responsibilities,
    }


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

        profile_dict = _profile_to_dict(profile)
        job_items = [{"job_id": j.id, "job": _job_to_dict(j)} for j in jobs]

        results = analyze_all(profile_dict, job_items, max_concurrency=5)
        ranking = aggregate_gaps(results)

        task.job_count = len(jobs)
        task.success_count = len([r for r in results if "error" not in r])
        task.ranking = ranking
        task.status = "done"
        task.finished_at = datetime.utcnow()
        db.commit()
    except Exception as e:
        db.rollback()
        task = db.query(models.BatchAnalysis).filter(models.BatchAnalysis.id == task_id).first()
        if task:
            task.status = "failed"
            task.error = str(e)
            task.finished_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


@router.post("/batch")
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

@router.post("/{job_id}", response_model=schemas.AnalysisOut)
def run_analysis(job_id: int, force: bool = False, db: Session = Depends(get_db)):
    profile = db.query(models.Profile).first()
    if not profile:
        raise HTTPException(status_code=400, detail="请先完善个人画像")

    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    profile_dict, job_dict = _profile_to_dict(profile), _job_to_dict(job)
    content_hash = _content_hash(profile_dict, job_dict)

    if not force:
        existing = (
            db.query(models.Analysis)
            .filter(models.Analysis.job_id == job_id, models.Analysis.content_hash == content_hash)
            .order_by(models.Analysis.created_at.desc())
            .first()
        )
        if existing:
            return existing

    result = analyze_match_v3(profile_dict, job_dict)

    breakdown = _clamp_breakdown(result.get("score_breakdown"))
    match_score = _weighted_score(breakdown) if breakdown else _clamp_score(result.get("match_score"))

    analysis = models.Analysis(
        job_id=job_id,
        content_hash=content_hash,
        match_score=match_score,
        score_breakdown=breakdown,
        matched_skills=result.get("matched_skills", []),
        missing_skills=result.get("missing_skills", []),
        strengths=result.get("strengths", []),
        gaps=result.get("gaps", []),
        action_items=result.get("action_items", []),
        summary=result.get("summary", ""),
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return analysis


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
