"""
analyze_match_v3：把 ai_service.py 里 v2 版本已经验证过的
analysis_chain / suggestion_chain 原样复用，用 LangGraph StateGraph
重新编排，而不是 v2 那种简单的链式 `|` 顺序调用，原因：

1. 加了 screen_node 规则筛选 + 条件路由（explain vs suggest）——
   纯规则判断（比如岗位强制要求 Java/Golang 这类候选人技术路线之外的
   语言）不需要走 LLM，用 StateGraph 的条件边比在 v2 的线性链里硬塞
   if/else 更清晰，命中规则时直接跳过建议生成，省一次 LLM 调用。
2. 加了显式的节点级 RetryPolicy（遇到 EmptyLLMOutput / ValidationError
   自动重试），比 v1 在 ai_service.py 里手写的一次性重试更规范、更好扩展。

v1/v2 为什么还留在 ai_service.py 里没删，见该文件顶部的注释。
analyze_match_v3 是当前 routers/analysis.py 实际调用的版本。
"""
from typing import TypedDict, Optional, Literal
from langgraph.graph import StateGraph, START, END
from langgraph.types import RetryPolicy
from pydantic import ValidationError

from .ai_service import analysis_chain, suggestion_chain
import json


class EmptyLLMOutput(Exception):
    """with_structured_output 返回 None 时抛出。

    不能继承 ValueError —— langgraph 的 default_retry_on 明确把 ValueError
    及其子类排除在重试范围外，继承 ValueError 会导致 RetryPolicy 形同虚设。
    """


EXCLUDED_SKILLS = ["java", "golang", "go语言"]


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
    hit = [k for k in EXCLUDED_SKILLS if k in text]
    return {"excluded_by": hit}


def analyze_node(state: MatchState):
    a = analysis_chain.invoke({"profile": state["profile"], "job": state["job"]})
    if a is None:
        raise EmptyLLMOutput("analysis_chain 未能返回结构化结果（返回 None）")
    return {"analysis": a.model_dump()}


def route_after_analyze(state: MatchState) -> Literal["suggest", "explain"]:
    return "explain" if state["excluded_by"] else "suggest"


def suggest_node(state: MatchState):
    gaps = state["analysis"]["gaps"]
    s = suggestion_chain.invoke({
        "profile": state["profile"],
        "job": state["job"],
        "gaps": json.dumps(gaps, ensure_ascii=False, indent=2),
    })
    if s is None:
        raise EmptyLLMOutput("suggestion_chain 未能返回结构化结果（返回 None）")
    return {"suggestion": s.model_dump()}


def explain_node(state: MatchState):
    """技术栈不匹配，不生成建议"""
    hit = "、".join(state["excluded_by"])
    return {"suggestion": {
        "gaps": [{**g, "suggestion": ""} for g in state["analysis"]["gaps"]],
        "action_items": [],
        "summary": f"该岗位必需技能包含 {hit}，与你的技术路线不符，未生成提升建议。匹配分和差距分析仅供参考。",
    }}


LLM_RETRY = RetryPolicy(max_attempts=3, retry_on=(ValidationError, EmptyLLMOutput))

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
    exact = (breakdown["skills"] * 0.4 + breakdown["experience"] * 0.3
             + breakdown["education"] * 0.15 + breakdown["other"] * 0.15)

    return {
        "match_score": int(exact + 0.5),
        "score_breakdown": breakdown,
        "matched_skills": a["matched_skills"],
        "missing_skills": a["missing_skills"],
        "strengths": a["strengths"],
        "gaps": s["gaps"],
        "action_items": s["action_items"],
        "summary": s["summary"],
    }
