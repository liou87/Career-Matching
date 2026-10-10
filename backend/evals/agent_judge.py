"""
AI 助手的回答依据检查：回答里关于用户数据的具体说法（岗位、匹配分、技能排行、
画像内容、偏好），能不能在工具返回、已保存的偏好或此前的对话里找到依据。

和差距检查一样，「有依据」必须摘录到原文，摘不出原文的按没有依据计。
"""
import json
from functools import lru_cache

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.llm.factory import get_model

# 第四阶段的 search_jobs 会返回命中片段，输出变长，资料上限要够裁判看全
MAX_CONTEXT_CHARS = 30000


class Claim(BaseModel):
    claim: str = Field(description="回答里的一条具体事实性说法")
    source: str = Field(description="资料里支撑这条说法的原文摘录；找不到写'无'")
    supported: bool = Field(description="资料里是否有依据")


class GroundingResult(BaseModel):
    claims: list[Claim] = Field(description="回答里所有关于用户数据的具体说法；没有就返回空列表")


GROUNDING_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "你是严格的事实核查员，只依据给定资料判断，不做任何推测。"),
    ("user", """用户的问题：
{question}

助手可以依据的资料（用户本轮的消息、工具返回结果、已保存的偏好、此前的对话）：
{context}

助手的回答：
{answer}

找出回答里关于用户数据的具体事实性说法，包括：岗位的名称、公司、城市、薪资、技能要求，
匹配分和差距，技能缺口排行和数字，画像内容，求职偏好，岗位数量。
以下不算，不要列出：通用的建议、解释、客套话；助手对自身能力、可用工具、
系统限制的描述（如"岗位库没有记录城市字段""搜索只匹配名称和技能"）；
对数字的主观评价（如"中等偏下""比较匹配"）。

对每条说法，在资料里找支撑它的原文填到 source，再判断 supported：
- 复述用户本轮消息里给出的内容，算有依据。
- 「没有某项」这类说法：资料里有对应的完整列表（如画像技能列表）且其中确实没有这一项，
  算有依据，source 写明依据的是哪个列表。
- 资料里找不到依据的（包括编出来的数字、岗位、技能），supported 为 false。"""),
])


@lru_cache
def grounding_chain():
    return GROUNDING_PROMPT | get_model("judge").with_structured_output(GroundingResult)


def judge_grounding(question: str, context: list[str], answer: str) -> list[dict]:
    if not answer.strip():
        return []
    text = "\n\n".join([f"用户本轮的消息：{question}", *context])
    out = grounding_chain().invoke({
        "question": question,
        "context": text[:MAX_CONTEXT_CHARS],
        "answer": answer,
    })
    if out is None:
        raise ValueError("裁判没有返回结构化结果")
    return [_consistent(c.model_dump()) for c in out.claims]


def _consistent(claim: dict) -> dict:
    """标了有依据却摘不出原文，按没有依据计并标记。"""
    if claim["supported"] and claim["source"].strip() in ("", "无"):
        return {**claim, "supported": False, "corrected": True}
    return claim


def context_from_turns(turns: list[dict], memories: list[str]) -> list[str]:
    """把多轮对话里的工具返回、此前的问答、已保存的偏好拼成裁判看的资料。"""
    parts = [f"已保存的求职偏好：{json.dumps(memories, ensure_ascii=False)}"] if memories else []
    for t in turns[:-1]:
        parts.append(f"此前用户问：{t['message']}\n此前助手答：{t['answer']}")
    for t in turns:
        parts.extend(f"工具 {o['name']} 返回：{o['content']}" for o in t["tool_outputs"])
    return parts
