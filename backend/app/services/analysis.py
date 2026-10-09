"""
单岗位匹配分析的业务逻辑：接口层和 AI 助手的 analyze_job 工具共用。
"""
import hashlib
import json

from sqlalchemy.orm import Session

from app.core.errors import DomainError, NotFoundError
from app.db import models
from app.graphs.match import analyze_match_v3
from app.services.scoring import clamp_breakdown, clamp_score, weighted_score


def profile_to_dict(profile: models.Profile) -> dict:
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


def job_to_dict(job: models.Job) -> dict:
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


def content_hash(profile: dict, job: dict) -> str:
    payload = json.dumps({"profile": profile, "job": job}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def analyze_job(db: Session, job_id: int, force: bool = False) -> models.Analysis:
    """分析一个岗位。画像和岗位都没变时直接复用上次结果，force=True 强制重跑。"""
    profile = db.query(models.Profile).first()
    if not profile:
        raise DomainError("请先完善个人画像")
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if not job:
        raise NotFoundError(f"岗位 {job_id} 不存在")

    profile_dict, job_dict = profile_to_dict(profile), job_to_dict(job)
    digest = content_hash(profile_dict, job_dict)

    if not force:
        existing = (
            db.query(models.Analysis)
            .filter(models.Analysis.job_id == job_id, models.Analysis.content_hash == digest)
            .order_by(models.Analysis.created_at.desc())
            .first()
        )
        if existing:
            return existing

    result = analyze_match_v3(profile_dict, job_dict)

    breakdown = clamp_breakdown(result.get("score_breakdown"))
    analysis = models.Analysis(
        job_id=job_id,
        content_hash=digest,
        match_score=weighted_score(breakdown) if breakdown else clamp_score(result.get("match_score")),
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
