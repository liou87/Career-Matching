from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime, JSON
from sqlalchemy.sql import func
from database import Base


class Profile(Base):
    __tablename__ = "profiles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100))
    education = Column(JSON)       # [{degree, school, major, year}]
    skills = Column(JSON)          # ["Python", "SQL", ...]
    experiences = Column(JSON)     # [{title, company, duration, description}]
    projects = Column(JSON)        # [{name, description, tech_stack}]
    target_roles = Column(JSON)    # ["数据分析师", "后端工程师"]
    target_cities = Column(JSON)   # ["北京", "上海"]
    target_companies = Column(JSON)  # ["字节跳动", "外企在华"]
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    raw_jd = Column(Text)          # 原始粘贴文本
    title = Column(String(200))
    company = Column(String(200))
    city = Column(String(100))
    salary_min = Column(Integer)   # 单位：千元/月
    salary_max = Column(Integer)
    required_skills = Column(JSON)
    preferred_skills = Column(JSON)
    experience_required = Column(String(100))
    education_required = Column(String(100))
    responsibilities = Column(JSON)
    parsed_at = Column(DateTime, server_default=func.now())
    source_url = Column(String(500))
    status = Column(String(50), default="active")  # active / archived


class Analysis(Base):
    __tablename__ = "analyses"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer)
    content_hash = Column(String(64), index=True)   # sha256(profile + job)，用于判断能否复用上次结果
    match_score = Column(Integer)       # 0-100
    score_breakdown = Column(JSON)      # {skills, experience, education, other}
    matched_skills = Column(JSON)
    missing_skills = Column(JSON)
    strengths = Column(JSON)
    gaps = Column(JSON)                 # [{gap, importance, suggestion}]
    action_items = Column(JSON)         # [{item, priority, resource}]
    summary = Column(Text)
    created_at = Column(DateTime, server_default=func.now())


class BatchAnalysis(Base):
    __tablename__ = "batch_analyses"

    id = Column(Integer, primary_key=True, index=True)
    status = Column(String, default="pending")   # pending/running/done/failed
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    job_count = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    ranking = Column(JSON, nullable=True)       # [{skill, job_count, category, originals}]
    error = Column(Text, nullable=True)


class Checklist(Base):
    __tablename__ = "checklist"

    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text)
    importance = Column(String(10))     # 高/中/低
    suggestion = Column(Text)
    status = Column(String(10), default="todo")   # todo / done
    category = Column(String(20), default="gap")  # gap（差距） / action（行动建议）
    created_at = Column(DateTime, server_default=func.now())
