"""
AI 助手的工具。

- 读工具直接执行。
- 写工具（WRITE_TOOLS）由 HumanInTheLoopMiddleware 拦截：模型发起调用后先中断，
  用户在界面上确认才真正执行，拒绝则不执行并把原因告诉模型。
"""
import json
from typing import Literal, Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.core.errors import DomainError
from app.db import models
from app.db.session import SessionLocal
from app.llm import embeddings
from app.services import analysis as analysis_service
from app.services import checklist as checklist_service
from app.services import interview as interview_service
from app.services import jobs as jobs_service
from app.services import retrieval

# ---------- 读工具 ----------


@tool
def search_jobs(query: str = "", city: Optional[str] = None, company: Optional[str] = None, limit: int = 5) -> str:
    """搜索岗位库。query 用自然语言或关键词描述想找的岗位（技能、方向、职责都行），
    按语义和关键词综合排序；city、company 按城市、公司筛选（包含即可）。
    query 留空时按筛选条件列出岗位。返回：
    - total：满足城市/公司筛选条件的岗位总数（不看 query）
    - matched：其中与 query 关键词相关的岗位数
    - results：按相关度排序的前 limit 条，含 id、标题、公司、城市、薪资、必需技能、命中的片段原文。
      排在后面的结果可能只是弱相关，以片段内容为准。"""
    db = SessionLocal()
    try:
        mode = "hybrid" if embeddings.enabled() else "keyword"
        out = retrieval.search(db, query, city=city, company=company, limit=max(1, min(limit, 15)), mode=mode)
        return json.dumps(out, ensure_ascii=False)
    finally:
        db.close()


@tool
def list_job_scores() -> str:
    """列出岗位库里所有岗位及最近一次的匹配分（还没分析过的为 null），按匹配分从高到低排序。
    回答「匹配分最高/最低的岗位」「哪些岗位还没分析」这类问题时用。"""
    db = SessionLocal()
    try:
        jobs = db.query(models.Job).filter(models.Job.status == "active").all()
        latest = {}
        for a in db.query(models.Analysis).order_by(models.Analysis.created_at).all():
            latest[a.job_id] = a.match_score
        rows = [{"id": j.id, "title": j.title, "company": j.company, "city": j.city,
                 "match_score": latest.get(j.id)} for j in jobs]
        rows.sort(key=lambda r: (r["match_score"] is None, -(r["match_score"] or 0)))
        return json.dumps({"total": len(rows), "jobs": rows}, ensure_ascii=False)
    finally:
        db.close()


@tool
def get_skill_ranking() -> str:
    """读最近一条 status=done 的 BatchAnalysis 的 ranking，只返回 skill 和 job_count（不要 originals，太长），没有则返回提示"""
    db = SessionLocal()
    try:
        task = (
            db.query(models.BatchAnalysis)
            .filter(models.BatchAnalysis.status == "done")
            .order_by(models.BatchAnalysis.created_at.desc())
            .first()
        )
        if not task or not task.ranking:
            return "还没有技能缺口分析结果，请先在「技能缺口总览」页面跑一次批量分析"
        simplified = [{"skill": r["skill"], "job_count": r["job_count"]} for r in task.ranking]
        return json.dumps(simplified, ensure_ascii=False)
    finally:
        db.close()


@tool
def get_profile() -> str:
    """读 profiles 表第一条"""
    db = SessionLocal()
    try:
        profile = db.query(models.Profile).first()
        if not profile:
            return "还没有填写个人画像"
        return json.dumps(analysis_service.profile_to_dict(profile), ensure_ascii=False)
    finally:
        db.close()


@tool
def get_job_analysis(job_id: int) -> str:
    """读该岗位最近一条 analyses 记录，返回 match_score/gaps/action_items，没有则返回提示"""
    db = SessionLocal()
    try:
        analysis = (
            db.query(models.Analysis)
            .filter(models.Analysis.job_id == job_id)
            .order_by(models.Analysis.created_at.desc())
            .first()
        )
        if not analysis:
            return f"岗位 {job_id} 还没有分析记录，请先在「匹配分析」页面跑一次"
        data = {
            "match_score": analysis.match_score,
            "gaps": analysis.gaps,
            "action_items": analysis.action_items,
        }
        return json.dumps(data, ensure_ascii=False)
    finally:
        db.close()


# ---------- 写工具（执行前需要用户确认） ----------


class ChecklistEntry(BaseModel):
    content: str = Field(description="要做的事，具体可执行")
    importance: Optional[Literal["高", "中", "低"]] = Field(default=None, description="重要程度")
    category: Literal["gap", "action"] = Field(default="action", description="gap：差距；action：行动建议")


@tool
def add_to_checklist(items: list[ChecklistEntry]) -> str:
    """把差距或行动建议加入用户的提升清单。调用后系统会先请用户确认，确认后才真正写入。"""
    db = SessionLocal()
    try:
        rows = checklist_service.add_items(db, [i.model_dump() for i in items])
        return f"已加入提升清单 {len(rows)} 条：" + "；".join(r.content for r in rows)
    finally:
        db.close()


@tool
def analyze_job(job_id: int, force: bool = False) -> str:
    """对一个岗位跑匹配分析（约 10 秒，会调用大模型）。画像和岗位没变时复用上次结果，
    用户明确要求「重新分析」时 force 设为 true。调用后系统会先请用户确认。"""
    db = SessionLocal()
    try:
        a = analysis_service.analyze_job(db, job_id, force=force)
        return json.dumps({
            "job_id": job_id,
            "match_score": a.match_score,
            "missing_skills": a.missing_skills,
            "gaps": [g["gap"] for g in a.gaps or []],
            "action_items": [x["item"] for x in a.action_items or []],
            "summary": a.summary,
        }, ensure_ascii=False)
    except DomainError as e:
        return e.message
    finally:
        db.close()


@tool
def add_job(raw_jd: str) -> str:
    """把用户粘贴的 JD 原文解析后加入岗位库（会调用大模型解析）。调用后系统会先请用户确认。"""
    db = SessionLocal()
    try:
        job = jobs_service.create_job(db, raw_jd)
        return json.dumps({"id": job.id, "title": job.title, "company": job.company, "city": job.city},
                          ensure_ascii=False)
    finally:
        db.close()


@tool
def generate_interview_questions(job_id: int, force: bool = False) -> str:
    """为一个岗位生成面试题和答题要点（会调用大模型，需要这个岗位已有匹配分析）。
    已生成过且画像、岗位没变时直接返回上次的结果；用户要求重新生成时 force 设为 true。
    调用后系统会先请用户确认。"""
    db = SessionLocal()
    try:
        record = interview_service.generate(db, job_id, force=force)
        return json.dumps([
            {"question": q["question"], "relation": q["relation"], "jd_requirement": q["jd_requirement"],
             "answer_points": q["answer_points"]}
            for q in record.questions
        ], ensure_ascii=False)
    except DomainError as e:
        return e.message
    finally:
        db.close()


READ_TOOLS = [search_jobs, list_job_scores, get_skill_ranking, get_profile, get_job_analysis]
WRITE_TOOLS = [add_to_checklist, analyze_job, add_job, generate_interview_questions]
