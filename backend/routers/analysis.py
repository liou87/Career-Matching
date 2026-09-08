import hashlib
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from services.graph import analyze_match_v3
import models, schemas

router = APIRouter(prefix="/analysis", tags=["analysis"])


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
