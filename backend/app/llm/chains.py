"""
匹配分析的两条链：节点1 客观比对打分，节点2 基于已识别的差距生成建议。

线上的 v3（graphs/match.py）用 analysis_chain / suggestion_chain。
对照实验 v2（llm/legacy.py）用冻结的 analysis_chain_v2，保证历史评测可以复现：
之后对分析 prompt 的改动只进 v3。
"""
from functools import lru_cache

from langchain_core.prompts import ChatPromptTemplate

from app.llm.factory import get_model
from app.llm.schemas import AnalysisResult, SuggestionResult

_ANALYSIS_SYSTEM = "你是求职顾问，负责客观比对候选人与岗位。只做分析和打分，不要给任何建议。"
_ANALYSIS_USER = """候选人信息：
{profile}

目标岗位：
{job}

四个维度分别打分（0-100），不要给整体印象分。
gaps 要具体、落到点上，按 importance 从高到低排序。"""

# v2 冻结版本，不再修改
ANALYSIS_PROMPT_V2 = ChatPromptTemplate.from_messages([("system", _ANALYSIS_SYSTEM), ("user", _ANALYSIS_USER)])

# v3：评测发现模型会把多选一要求里的其他选项列为缺失（误报缺失约 3.6%），加一条约束
ANALYSIS_PROMPT = ChatPromptTemplate.from_messages([
    ("system", _ANALYSIS_SYSTEM),
    ("user", _ANALYSIS_USER + """
missing_skills 和 gaps 只写候选人确实缺少的。JD 里多选一的要求（如"Python/Java/Scala"、
"LangGraph/Google ADK"、"至少一种编程语言（如Java、Python等）"），候选人满足其中任意一项就算满足，
不要把其余选项列为缺失。"""),
])

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


@lru_cache
def analysis_chain():
    return ANALYSIS_PROMPT | get_model("analysis").with_structured_output(AnalysisResult)


@lru_cache
def analysis_chain_v2():
    return ANALYSIS_PROMPT_V2 | get_model("analysis").with_structured_output(AnalysisResult)


@lru_cache
def suggestion_chain():
    return SUGGESTION_PROMPT | get_model("suggest").with_structured_output(SuggestionResult)
