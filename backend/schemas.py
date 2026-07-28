from pydantic import BaseModel
from typing import Optional
from datetime import datetime


# ---------- Profile ----------

class Education(BaseModel):
    degree: str
    school: str
    major: str
    year: Optional[str] = None

class Experience(BaseModel):
    title: str
    company: str
    duration: str
    description: Optional[str] = None

class Project(BaseModel):
    name: str
    description: str
    tech_stack: list[str] = []

class ProfileCreate(BaseModel):
    name: str
    education: list[Education] = []
    skills: list[str] = []
    experiences: list[Experience] = []
    projects: list[Project] = []
    target_roles: list[str] = []
    target_cities: list[str] = []
    target_companies: list[str] = []

class ProfileOut(ProfileCreate):
    id: int
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ---------- Job ----------

class JobCreate(BaseModel):
    raw_jd: str
    source_url: Optional[str] = None

class JobOut(BaseModel):
    id: int
    raw_jd: str
    title: Optional[str] = None
    company: Optional[str] = None
    city: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    required_skills: Optional[list] = []
    preferred_skills: Optional[list] = []
    experience_required: Optional[str] = None
    education_required: Optional[str] = None
    responsibilities: Optional[list] = []
    source_url: Optional[str] = None
    status: str = "active"
    parsed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ---------- Analysis ----------

class Gap(BaseModel):
    gap: str
    importance: str   # 高 / 中 / 低
    suggestion: str

class ActionItem(BaseModel):
    item: str
    priority: str   # high / medium / low
    resource: Optional[str] = None

class AnalysisOut(BaseModel):
    id: int
    job_id: int
    match_score: int
    matched_skills: list[str] = []
    missing_skills: list[str] = []
    strengths: list[str] = []
    gaps: list[Gap] = []
    action_items: list[ActionItem] = []
    summary: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ---------- Checklist ----------

class ChecklistItemCreate(BaseModel):
    content: str
    importance: Optional[str] = None
    suggestion: Optional[str] = None

class ChecklistCreate(BaseModel):
    items: list[ChecklistItemCreate]

class ChecklistUpdate(BaseModel):
    content: Optional[str] = None
    status: Optional[str] = None   # todo / done

class ChecklistOut(BaseModel):
    id: int
    content: str
    importance: Optional[str] = None
    suggestion: Optional[str] = None
    status: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
