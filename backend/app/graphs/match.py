"""
analyze_match_v3：把 llm/chains.py 里 v2 版本已经验证过的
analysis_chain / suggestion_chain 原样复用，用 LangGraph StateGraph
重新编排，而不是 v2 那种简单的链式 `|` 顺序调用，原因：

1. 加了 screen_node 规则筛选 + 条件路由（explain vs suggest）——
   纯规则判断（比如岗位强制要求 Java/Golang 这类候选人技术路线之外的
   语言）不需要走 LLM，用 StateGraph 的条件边比在 v2 的线性链里硬塞
   if/else 更清晰，命中规则时直接跳过建议生成，省一次 LLM 调用。
2. 加了显式的节点级 RetryPolicy（遇到 EmptyLLMOutput / ValidationError
   自动重试），比 v1 在 llm/legacy.py 里手写的一次性重试更规范、更好扩展。

v1/v2 为什么还留着没删，见 llm/legacy.py 顶部的注释。
analyze_match_v3 是当前 api/analysis.py 实际调用的版本。
"""
import json
from typing import Literal, Optional, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy
from pydantic import ValidationError

from app.core.config import settings
from app.core.errors import LLMOutputError
from app.llm import chains
from app.services.scoring import weighted_score


class MatchState(TypedDict):
    profile: str          # json 字符串
    job: str              # json 字符串
    job_raw: dict                    # 规则判断用的原始 job dict
    excluded_by: Optional[list]      # 命中的排除项
    analysis: Optional[dict]     # 节点1 产出
    suggestion: Optional[dict]   # 节点2 产出（或 explain 节点产出）


def screen_node(state: MatchState):
    """规则筛选，不调 LLM"""
    required = state["job_raw"].get("required_skills") or []
    text = " ".join(str(s) for s in required).lower()
    hit = [k for k in settings.excluded_skills if k in text]
    return {"excluded_by": hit}


def analyze_node(state: MatchState):
    a = chains.analysis_chain().invoke({"profile": state["profile"], "job": state["job"]})
    if a is None:
        raise LLMOutputError("analysis_chain 未能返回结构化结果（返回 None）")
    return {"analysis": a.model_dump()}


def route_after_analyze(state: MatchState) -> Literal["suggest", "explain"]:
    return "explain" if state["excluded_by"] else "suggest"


def suggest_node(state: MatchState):
    gaps = state["analysis"]["gaps"]
    s = chains.suggestion_chain().invoke({
        "profile": state["profile"],
        "job": state["job"],
        "gaps": json.dumps(gaps, ensure_ascii=False, indent=2),
    })
    if s is None:
        raise LLMOutputError("suggestion_chain 未能返回结构化结果（返回 None）")
    return {"suggestion": s.model_dump()}


def explain_node(state: MatchState):
    """技术栈不匹配，不生成建议"""
    hit = "、".join(state["excluded_by"])
    return {"suggestion": {
        "gaps": [{**g, "suggestion": ""} for g in state["analysis"]["gaps"]],
        "action_items": [],
        "summary": f"该岗位必需技能包含 {hit}，与你的技术路线不符，未生成提升建议。匹配分和差距分析仅供参考。",
    }}


LLM_RETRY = RetryPolicy(max_attempts=3, retry_on=(ValidationError, LLMOutputError))

_g = StateGraph(MatchState)
_g.add_node("screen", screen_node)
_g.add_node("analyze", analyze_node, retry_policy=LLM_RETRY)
_g.add_node("suggest", suggest_node, retry_policy=LLM_RETRY)
_g.add_node("explain", explain_node)

_g.add_edge(START, "screen")
_g.add_edge("screen", "analyze")
_g.add_conditional_edges("analyze", route_after_analyze, {
    "suggest": "suggest",
    "explain": "explain",
})
_g.add_edge("suggest", END)
_g.add_edge("explain", END)
match_graph = _g.compile()


def analyze_match_v3(profile: dict, job: dict) -> dict:
    result = match_graph.invoke({
        "profile": json.dumps(profile, ensure_ascii=False, indent=2),
        "job": json.dumps(job, ensure_ascii=False, indent=2),
        "job_raw": job,
        "excluded_by": None,
        "analysis": None,
        "suggestion": None,
    })

    a = result["analysis"]
    s = result["suggestion"]

    breakdown = {
        "skills": a["skills_score"],
        "experience": a["experience_score"],
        "education": a["education_score"],
        "other": a["other_score"],
    }

    return {
        "match_score": weighted_score(breakdown),
        "score_breakdown": breakdown,
        "matched_skills": a["matched_skills"],
        "missing_skills": a["missing_skills"],
        "strengths": a["strengths"],
        "gaps": s["gaps"],
        "action_items": s["action_items"],
        "summary": s["summary"],
    }
