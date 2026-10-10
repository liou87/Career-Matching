from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from app.db.session import Base


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


class LLMCall(Base):
    """每次 LLM 调用一条记录，是线上指标（成功率、耗时、成本）的数据来源。"""
    __tablename__ = "llm_calls"

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    request_id = Column(String(32), index=True)   # 同一个请求里的多次调用共用一个
    role = Column(String(20))                     # jd_parse / analysis / suggest / merge / agent / judge
    model = Column(String(50))
    ok = Column(Boolean)
    latency_ms = Column(Integer)
    input_tokens = Column(Integer)
    cached_input_tokens = Column(Integer)          # 命中 DeepSeek 上下文缓存的输入，价格低得多
    output_tokens = Column(Integer)
    error = Column(String(300))


class JobChunk(Base):
    """岗位检索用的片段：每个岗位按字段切成几段，各存一份文本和向量。
    向量存成普通 JSON 列、在 Python 里算相似度：岗位只有几十到几百个时足够快，
    本地 SQLite 和线上 Postgres 共用一套代码。规模大了再换 pgvector。"""
    __tablename__ = "job_chunks"

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, index=True)
    field = Column(String(30))          # header / required / preferred / requirements / responsibility
    text = Column(Text)
    embedding = Column(JSON)            # 没有 embedding 服务或计算失败时为空，只参与关键词检索
    embedding_model = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)


class AIRequest(Base):
    """每次调用 AI 的接口请求一条记录，用于按 IP 限流。"""
    __tablename__ = "ai_requests"

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    client_ip = Column(String(64), index=True)
    path = Column(String(200))


class InterviewPrepRecord(Base):
    """面试题生成结果。画像、岗位、参考的分析都没变时直接复用。"""
    __tablename__ = "interview_preps"

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, index=True)
    content_hash = Column(String(64), index=True)
    analysis_id = Column(Integer)
    questions = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
