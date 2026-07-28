from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from services.ai_service import analyze_match
import models, schemas

router = APIRouter(prefix="/analysis", tags=["analysis"])


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
def run_analysis(job_id: int, db: Session = Depends(get_db)):
    profile = db.query(models.Profile).first()
    if not profile:
        raise HTTPException(status_code=400, detail="请先完善个人画像")

    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    result = analyze_match(_profile_to_dict(profile), _job_to_dict(job))

    analysis = models.Analysis(
        job_id=job_id,
        match_score=result["match_score"],
        matched_skills=result.get("matched_skills", []),
        missing_skills=result.get("missing_skills", []),
        strengths=result.get("strengths", []),
        gaps=result.get("gaps", []),
        suggestions=result.get("suggestions", []),
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
