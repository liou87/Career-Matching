"""
批量并发版：用 LangGraph 的 Send API 把 analyze_match_v3 fan-out 到多个岗位
并发跑，而不是像单岗位分析那样一次只处理一个。这里只是编排层，实际分析
逻辑完全复用 graphs/match.py 里已经验证过的 analyze_match_v3，不重复实现。

调用方：api/analysis.py 的批量分析接口、evals/batch_eval.py。
"""
import json
import operator
from typing import TypedDict, Annotated

from langgraph.graph import StateGraph, START, END
from langgraph.types import Send

from app.core.config import settings
from app.graphs.match import analyze_match_v3


class BatchState(TypedDict):
    profile: str                              # json 字符串，避免每个 fan-out 分支重复序列化
    jobs: list[dict]                          # 每项 {"job_id": int, "job": dict}，job_id 只用于结果归属，不进 job dict
    results: Annotated[list, operator.add]    # 各分支各自返回一条，靠 operator.add 汇总


def fan_out(state: BatchState):
    return [
        Send("analyze_one", {"profile": state["profile"], "job": item["job"], "job_id": item["job_id"]})
        for item in state["jobs"]
    ]


def analyze_one(state: dict) -> dict:
    job = state["job"]
    job_id = state["job_id"]
    try:
        profile = json.loads(state["profile"])
        result = analyze_match_v3(profile, job)
        result["job_id"] = job_id
        return {"results": [result]}
    except Exception as e:
        return {"results": [{"job_id": job_id, "error": str(e)}]}


_g = StateGraph(BatchState)
_g.add_node("analyze_one", analyze_one)
_g.add_conditional_edges(START, fan_out, ["analyze_one"])
_g.add_edge("analyze_one", END)
batch_graph = _g.compile()


def analyze_all(profile: dict, jobs: list[dict], max_concurrency: int | None = None) -> list[dict]:
    initial_state = {
        "profile": json.dumps(profile, ensure_ascii=False),
        "jobs": jobs,
        "results": [],
    }
    concurrency = max_concurrency or settings.batch_max_concurrency
    final_state = batch_graph.invoke(initial_state, config={"max_concurrency": concurrency})
    return final_state["results"]
