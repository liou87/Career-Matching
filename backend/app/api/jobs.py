from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas
from app.db import models
from app.db.session import get_db
from app.services.jobs import create_job

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=list[schemas.JobOut])
def list_jobs(db: Session = Depends(get_db)):
    return db.query(models.Job).filter(models.Job.status == "active").order_by(models.Job.parsed_at.desc()).all()


@router.post("", response_model=schemas.JobOut)
def add_job(data: schemas.JobCreate, db: Session = Depends(get_db)):
    return create_job(db, data.raw_jd, data.source_url)


@router.get("/{job_id}", response_model=schemas.JobOut)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.delete("/{job_id}")
def delete_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    job.status = "archived"
    db.commit()
    return {"ok": True}
