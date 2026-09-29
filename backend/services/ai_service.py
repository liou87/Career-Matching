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

analyze_match_v3（在 services/graph.py 里，用 LangGraph 把这里的
analysis_chain / suggestion_chain 原样复用、重新编排成状态图，加了规则
筛选、条件路由和节点级重试）是当前 routers/analysis.py 实际调用的版本。

parse_jd 走的是裸 openai SDK（json_object 模式），跟上面这套 LangChain
链路是完全独立的另一个功能（JD 解析，不是匹配分析），不存在 v1/v2/v3 之分。
"""
import os
import json
from openai import OpenAI
from dotenv import load_dotenv

from langchain_deepseek import ChatDeepSeek
from langchain_core.prompts import ChatPromptTemplate
from .schemas import MatchResult, AnalysisResult, SuggestionResult

load_dotenv()

#  SDK
client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
)
MODEL = "deepseek-chat"


def _ask_json(prompt: str, max_tokens: int) -> dict:
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=max_tokens,
        temperature=0,
        seed=42,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)


def parse_jd(raw_jd: str) -> dict:
    prompt = f"""请解析以下招聘JD，提取结构化信息，返回严格的JSON格式，不要有任何多余文字。

JD原文：
{raw_jd}

返回格式：
{{
  "title": "职位名称",
  "company": "公司名称",
  "city": "城市（多城市用逗号分隔）",
  "salary_min": 月薪下限（整数，单位千元，无法确定填null）,
  "salary_max": 月薪上限（整数，单位千元，无法确定填null）,
  "required_skills": ["必须技能1", "必须技能2"],
  "preferred_skills": ["加分技能1", "加分技能2"],
  "experience_required": "经验要求，如'1-3年'或'应届生可'",
  "education_required": "学历要求，如'本科及以上'",
  "responsibilities": ["职责1", "职责2", "职责3"]
}}"""

    return _ask_json(prompt, 1024)


#  LangChain
llm = ChatDeepSeek(model="deepseek-chat", max_tokens=2048, temperature=0)

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

match_chain = MATCH_PROMPT | llm.with_structured_output(MatchResult)


def analyze_match_v1(profile: dict, job: dict) -> dict:
    payload = {
        "profile": json.dumps(profile, ensure_ascii=False, indent=2),
        "job": json.dumps(job, ensure_ascii=False, indent=2),
    }

    result = match_chain.invoke(payload)
    if result is None:
        # DeepSeek 偶尔不会触发 tool call，with_structured_output 这时返回 None，重试一次
        result = match_chain.invoke(payload)
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


# ---------- B2: 两步拆分（节点1 客观比对 -> 节点2 生成建议） ----------

ANALYSIS_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "你是求职顾问，负责客观比对候选人与岗位。只做分析和打分，不要给任何建议。"),
    ("user", """候选人信息：
{profile}

目标岗位：
{job}

四个维度分别打分（0-100），不要给整体印象分。
gaps 要具体、落到点上，按 importance 从高到低排序。"""),
])

analysis_chain = ANALYSIS_PROMPT | llm.with_structured_output(AnalysisResult)

SUGGESTION_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "你是求职顾问，基于已经分析好的差距，给出可执行的提升建议。"),
    ("user", """候选人已有项目和经历：
{profile}

目标岗位：
{job}

已识别的差距（原样保留 gap 和 importance，只补充 suggestion）：
{gaps}

要求：
- action_items 要说清"做什么"和"为什么这件事对这个岗位有含金量"。
- item 必须有可验证的产出物：代码、数据、上线地址、性能数字。
  反例："系统学习LangGraph"（无法验证做没做完）
  正例："用LangGraph重构匹配流程为状态图，并给出重构前后失败率的对比数据"
- why_valuable 要对应到JD里的具体要求，或说明这能证明什么能力，
  不要写"这是行业趋势"这类空话。
- 优先考虑能改造候选人已有项目的方向（成本低、能快速产出）；
  如果已有项目确实承载不了，可以提出新建，但要说明为什么必须新开。
- 只给真正有价值的建议。如果只有1条值得说，就只给1条。
- 不要写"争取实习""开源到GitHub""刷LeetCode"这类通用建议。"""),
])

suggestion_chain = SUGGESTION_PROMPT | llm.with_structured_output(SuggestionResult)


def analyze_match_v2(profile: dict, job: dict) -> dict:
    p = json.dumps(profile, ensure_ascii=False, indent=2)
    j = json.dumps(job, ensure_ascii=False, indent=2)

    a = analysis_chain.invoke({"profile": p, "job": j})

    suggestion_payload = {
        "profile": p,
        "job": j,
        "gaps": json.dumps([g.model_dump() for g in a.gaps], ensure_ascii=False, indent=2),
    }
    try:
        s = suggestion_chain.invoke(suggestion_payload)
    except Exception:
        # 结构化输出偶尔缺字段导致校验失败（见 job 11 复现），重试一次
        s = suggestion_chain.invoke(suggestion_payload)

    # 加权分在 Python 算，避开银行家舍入
    breakdown = {
        "skills": a.skills_score,
        "experience": a.experience_score,
        "education": a.education_score,
        "other": a.other_score,
    }
    exact = (breakdown["skills"] * 0.4 + breakdown["experience"] * 0.3
             + breakdown["education"] * 0.15 + breakdown["other"] * 0.15)
    match_score = int(exact + 0.5)      # 四舍五入，不用 round()

    return {
        "match_score": match_score,
        "score_breakdown": breakdown,
        "matched_skills": a.matched_skills,
        "missing_skills": a.missing_skills,
        "strengths": a.strengths,
        "gaps": [g.model_dump() for g in s.gaps],
        "action_items": [x.model_dump() for x in s.action_items],
        "summary": s.summary,
    }
