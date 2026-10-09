"""
这个文件里同时保留了 analyze_match_v1 和 analyze_match_v2 两个版本，
是刻意的对照实验，不是没清理干净的遗留代码：

- analyze_match_v1：单条 LangChain 链，一次结构化输出拿到所有字段
  （含 match_score，由 AI 自己算加权和）。
- analyze_match_v2：拆成两条链（节点1 客观打分识别差距 -> 节点2 基于候选人
  已有项目生成建议），match_score 改为在 Python 里按 score_breakdown 加权
  计算，并加了 why_valuable 字段和"禁止通用建议"的约束。

用 evals/baseline_eval.py 和 evals/two_stage_eval.py 实测对比过：v1 的
match_score 有约一半概率跟自己给出的四个子分算出来的加权值对不上（AI 自己
做加权求和有算术/舍入误差），v2 是 0 误差；action_items 质量也更高（0 条
命中"系统学习X"这类空话）。v1 保留下来是为了让这个对比可复现、可回归验证。

analyze_match_v3（在 graphs/match.py 里，用 LangGraph 把 llm/chains.py 的
analysis_chain / suggestion_chain 原样复用、重新编排成状态图，加了规则
筛选、条件路由和节点级重试）是当前 api/analysis.py 实际调用的版本。
"""
import json
from functools import lru_cache

from langchain_core.prompts import ChatPromptTemplate

from app.llm import chains
from app.llm.factory import get_model
from app.llm.schemas import MatchResult
from app.services.scoring import weighted_score

# ---------- v1：单条链，AI 自己算加权分 ----------
# prompt 里的权重是实验当时的写法，刻意不跟随 settings.score_weights 变化

MATCH_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "你是一个专业的求职顾问，分析候选人与岗位的匹配情况。"),
    ("user", """候选人信息：
{profile}

目标岗位：
{job}

评分要求：四个维度分别打分，不要直接给整体印象分。
match_score = round(skills_score*0.4 + experience_score*0.3 + education_score*0.15 + other_score*0.15)
gaps 每条要具体、落到点上（缺什么技能/经验/背景）。
action_items 每条要具体可执行。"""),
])


@lru_cache
def match_chain():
    return MATCH_PROMPT | get_model("analysis").with_structured_output(MatchResult)


def analyze_match_v1(profile: dict, job: dict) -> dict:
    payload = {
        "profile": json.dumps(profile, ensure_ascii=False, indent=2),
        "job": json.dumps(job, ensure_ascii=False, indent=2),
    }

    result = match_chain().invoke(payload)
    if result is None:
        # DeepSeek 偶尔不会触发 tool call，with_structured_output 这时返回 None，重试一次
        result = match_chain().invoke(payload)
    if result is None:
        raise RuntimeError("DeepSeek 未能返回结构化的匹配结果（重试一次后仍失败），请稍后再试")

    data = result.model_dump()
    data["score_breakdown"] = {
        "skills": data.pop("skills_score", 0),
        "experience": data.pop("experience_score", 0),
        "education": data.pop("education_score", 0),
        "other": data.pop("other_score", 0),
    }
    return data


# ---------- v2：两步拆分（节点1 客观比对 -> 节点2 生成建议） ----------

def analyze_match_v2(profile: dict, job: dict) -> dict:
    p = json.dumps(profile, ensure_ascii=False, indent=2)
    j = json.dumps(job, ensure_ascii=False, indent=2)

    a = chains.analysis_chain_v2().invoke({"profile": p, "job": j})

    suggestion_payload = {
        "profile": p,
        "job": j,
        "gaps": json.dumps([g.model_dump() for g in a.gaps], ensure_ascii=False, indent=2),
    }
    try:
        s = chains.suggestion_chain().invoke(suggestion_payload)
    except Exception:
        # 结构化输出偶尔缺字段导致校验失败（见 job 11 复现），重试一次
        s = chains.suggestion_chain().invoke(suggestion_payload)

    breakdown = {
        "skills": a.skills_score,
        "experience": a.experience_score,
        "education": a.education_score,
        "other": a.other_score,
    }

    return {
        # 加权分在 Python 算
        "match_score": weighted_score(breakdown),
        "score_breakdown": breakdown,
        "matched_skills": a.matched_skills,
        "missing_skills": a.missing_skills,
        "strengths": a.strengths,
        "gaps": [g.model_dump() for g in s.gaps],
        "action_items": [x.model_dump() for x in s.action_items],
        "summary": s.summary,
    }
