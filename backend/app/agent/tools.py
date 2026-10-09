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
from app.services import analysis as analysis_service
from app.services import checklist as checklist_service
from app.services import jobs as jobs_service

# ---------- 读工具（与第三阶段之前完全一致，保证评测前后可比） ----------


@tool
def search_jobs(keyword: str) -> str:
    """查 jobs 表，title/company/required_skills/preferred_skills 模糊匹配，返回 id/title/company/required_skills/preferred_skills，最多5条，json 字符串"""
    db = SessionLocal()
    try:
        # JSON 列在库里是 \uXXXX 转义存的，SQL LIKE 匹配不到中文技能，
        # 所以取出活跃岗位后在 Python 里对解码后的字段做匹配
        kw = keyword.lower()
        jobs = [
            j for j in db.query(models.Job).filter(models.Job.status == "active").all()
            if kw in " ".join([
                j.title or "",
                j.company or "",
                *(j.required_skills or []),
                *(j.preferred_skills or []),
            ]).lower()
        ][:5]
        result = [
            {
                "id": j.id,
                "title": j.title,
                "company": j.company,
                "required_skills": j.required_skills,
                "preferred_skills": j.preferred_skills,
            }
            for j in jobs
        ]
        return json.dumps(result, ensure_ascii=False)
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


READ_TOOLS = [search_jobs, get_skill_ranking, get_profile, get_job_analysis]
WRITE_TOOLS = [add_to_checklist, analyze_job, add_job]
