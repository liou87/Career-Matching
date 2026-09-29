import json

from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_core.messages import AIMessage, HumanMessage

from database import SessionLocal
import models
from .ai_service import llm


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
        data = {
            "name": profile.name,
            "education": profile.education,
            "skills": profile.skills,
            "experiences": profile.experiences,
            "projects": profile.projects,
            "target_roles": profile.target_roles,
            "target_cities": profile.target_cities,
            "target_companies": profile.target_companies,
        }
        return json.dumps(data, ensure_ascii=False)
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


SYSTEM = """你是 CareerMatch 的求职问答助手，基于用户已有的岗位库、个人画像和历史分析结果回答问题。

可用工具：
- search_jobs：按关键词模糊搜索岗位库里的岗位（title/company/required_skills/preferred_skills 都会匹配）
- get_skill_ranking：查最近一次批量分析得到的技能缺口排行
- get_profile：查看用户的个人画像
- get_job_analysis：查看某个岗位的匹配分析结果（需要 job_id；不确定 job_id 时先用 search_jobs 查到）

规则：
- 涉及具体数据（岗位、技能、分数、画像内容）时必须调用工具获取，不要凭空编造。
- 工具返回"还没有"这类提示时，直接告诉用户去对应页面先生成数据，不要编造内容替代。
- 描述用户已有技能时，只列 get_profile 返回的内容，不要推测或补充。
- 回答用简体中文，简洁直接。
"""

agent = create_agent(
    model=llm,
    tools=[search_jobs, get_skill_ranking, get_profile, get_job_analysis],
    system_prompt=SYSTEM,
)


def chat(message: str, history: list) -> dict:
    messages = []
    for h in history:
        role = h.get("role")
        content = h.get("content", "")
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))
    messages.append(HumanMessage(content=message))

    result = agent.invoke({"messages": messages})
    result_messages = result["messages"]

    reply = ""
    for m in reversed(result_messages):
        if isinstance(m, AIMessage):
            reply = m.content
            break

    tool_calls = []
    for m in result_messages:
        if isinstance(m, AIMessage) and m.tool_calls:
            for tc in m.tool_calls:
                tool_calls.append({"name": tc["name"], "args": tc["args"]})

    return {"reply": reply, "tool_calls": tool_calls}
