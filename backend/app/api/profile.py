from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app import schemas
from app.db import models
from app.db.session import get_db

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=schemas.ProfileOut)
def get_profile(db: Session = Depends(get_db)):
    profile = db.query(models.Profile).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@router.put("", response_model=schemas.ProfileOut)
def upsert_profile(data: schemas.ProfileCreate, db: Session = Depends(get_db)):
    profile = db.query(models.Profile).first()
    if profile:
        for key, value in data.model_dump().items():
            setattr(profile, key, value)
    else:
        profile = models.Profile(**data.model_dump())
        db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile
