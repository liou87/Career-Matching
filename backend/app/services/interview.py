"""
面试题生成：从 JD 的要求出发出题，用这个岗位最近一次匹配分析的优势和差距排优先级，
答题要点只能引用画像里真实存在的经历。接口层和 AI 助手的工具共用。
"""
import json
from functools import lru_cache

from langchain_core.prompts import ChatPromptTemplate
from sqlalchemy.orm import Session

from app.core.errors import DomainError, LLMOutputError, NotFoundError
from app.db import models
from app.llm.factory import get_model
from app.llm.schemas import InterviewPrep
from app.services.analysis import content_hash, job_to_dict, profile_to_dict

INTERVIEW_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "你是资深技术面试官，帮候选人准备一场针对具体岗位的面试。"),
    ("user", """目标岗位（JD）：
{job}

候选人画像：
{profile}

这个岗位的匹配分析结论：
- 优势：{strengths}
- 差距：{gaps}

请出 6 到 10 道这个岗位的面试官最可能问的题：
- 题目从 JD 的要求出发，每题先在 jd_requirement 里原样摘录它考察的 JD 要求；
  优先覆盖必需技能和核心职责。
- 用匹配分析排优先级：差距相关的要求一定要问到（面试官会追问短板），
  优势相关的题给候选人展示的机会。
- 答题要点只能引用画像里真实存在的项目、技能和经历，不要替候选人编造经历；
  差距题写如何坦诚说明现状，以及具体的补齐计划。
- 不要出自我介绍、优缺点、职业规划这类通用题。"""),
])


@lru_cache
def interview_chain():
    return INTERVIEW_PROMPT | get_model("interview").with_structured_output(InterviewPrep)


def generate(db: Session, job_id: int, force: bool = False) -> models.InterviewPrepRecord:
    profile = db.query(models.Profile).first()
    if not profile:
        raise DomainError("请先完善个人画像")
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if not job:
        raise NotFoundError(f"岗位 {job_id} 不存在")
    analysis = (
        db.query(models.Analysis).filter(models.Analysis.job_id == job_id)
        .order_by(models.Analysis.created_at.desc()).first()
    )
    if not analysis:
        raise DomainError("请先对这个岗位做一次匹配分析，面试题会参考分析出的优势和差距")

    profile_dict, job_dict = profile_to_dict(profile), job_to_dict(job)
    digest = content_hash({**profile_dict, "analysis_id": analysis.id}, job_dict)
    if not force:
        cached = (
            db.query(models.InterviewPrepRecord)
            .filter(models.InterviewPrepRecord.job_id == job_id, models.InterviewPrepRecord.content_hash == digest)
            .order_by(models.InterviewPrepRecord.created_at.desc()).first()
        )
        if cached:
            return cached

    out = interview_chain().invoke({
        "job": json.dumps(job_dict, ensure_ascii=False, indent=2),
        "profile": json.dumps(profile_dict, ensure_ascii=False, indent=2),
        "strengths": json.dumps(analysis.strengths or [], ensure_ascii=False),
        "gaps": json.dumps([g.get("gap") for g in analysis.gaps or []], ensure_ascii=False),
    })
    if out is None:
        raise LLMOutputError("面试题生成没有返回结构化结果")

    record = models.InterviewPrepRecord(
        job_id=job_id, content_hash=digest, analysis_id=analysis.id,
        questions=[q.model_dump() for q in out.questions],
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def latest(db: Session, job_id: int) -> models.InterviewPrepRecord:
    record = (
        db.query(models.InterviewPrepRecord).filter(models.InterviewPrepRecord.job_id == job_id)
        .order_by(models.InterviewPrepRecord.created_at.desc()).first()
    )
    if not record:
        raise NotFoundError("这个岗位还没有生成过面试题")
    return record
