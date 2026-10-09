"""
裁判模型（settings.model_judge，比被测模型更强）做的两项检查，都不需要人工标注：

- 编造检测：建议有没有把画像里不存在的经历、项目、技能说成候选人已有的。
  「建议去做一件事」不算编造，只有「把没有的东西说成已有」才算。
- 差距检查：模型给出的每条缺失技能，是 JD 确实要求的真实差距、JD 里根本没有的
  凭空差距，还是画像里其实已经具备的误报。

LLM 当裁判有误判的可能，结论只用于版本间的相对比较，见 docs/evals.md。
"""
import json
from functools import lru_cache
from typing import Literal

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.llm.factory import get_model


class ItemVerdict(BaseModel):
    index: int = Field(description="对应输入里建议的序号")
    fabricated: bool = Field(description="是否把画像中不存在的经历、项目、技能或成果说成候选人已有的")
    evidence: str = Field(description="一句话说明依据：编造时指出画像里找不到的内容；否则写'无'")


class JudgeResult(BaseModel):
    verdicts: list[ItemVerdict] = Field(description="每条建议一个判断，不能遗漏")


JUDGE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "你是严格的事实核查员，只依据给定的候选人画像判断，不做任何推测。"),
    ("user", """候选人画像：
{profile}

待核查的建议（带序号）：
{items}

判断标准：
- 建议候选人「去做」某件事、「去学」某项技能，不算编造。
- 只有当建议把画像里没有的项目、经历、技能或成果说成候选人已经具备的，才算编造。
  例：画像里没有 Kafka，建议写"基于你在 CareerMatch 中的 Kafka 经验……"，算编造。
- 引用画像里确实存在的项目名、技能名，不算编造。

每条建议都要给出判断，index 与输入序号一一对应。"""),
])


@lru_cache
def judge_chain():
    return JUDGE_PROMPT | get_model("judge").with_structured_output(JudgeResult)


def suggestion_texts(result: dict) -> list[str]:
    """一次分析里所有需要核查的建议：行动建议和每条差距下的一句话建议。"""
    texts = []
    for a in result.get("action_items") or []:
        parts = [a.get("item"), a.get("why_valuable"), a.get("resource")]
        texts.append(" / ".join(p for p in parts if p))
    for g in result.get("gaps") or []:
        if g.get("suggestion"):
            texts.append(g["suggestion"])
    return texts


def judge(profile: dict, result: dict) -> list[dict]:
    """返回每条建议的判断；裁判输出条数对不上时抛错，不静默丢数据。"""
    texts = suggestion_texts(result)
    if not texts:
        return []
    out = judge_chain().invoke({
        "profile": json.dumps(profile, ensure_ascii=False, indent=2),
        "items": "\n".join(f"{i}. {t}" for i, t in enumerate(texts)),
    })
    if out is None or sorted(v.index for v in out.verdicts) != list(range(len(texts))):
        raise ValueError(f"裁判输出与 {len(texts)} 条建议对不上")
    return [{"text": texts[v.index], **v.model_dump()} for v in sorted(out.verdicts, key=lambda v: v.index)]


# ---------- 差距检查（不需要人工标注） ----------

class GapVerdict(BaseModel):
    index: int = Field(description="对应输入里缺失技能的序号")
    # 先找依据再下结论：字段顺序就是模型生成的顺序
    jd_source: str = Field(description="JD 的必需技能、加分技能或职责里与这一项对应的原文，原样摘录；确实找不到写'无'")
    category: Literal["valid", "not_required", "already_has"] = Field(
        description="valid：JD 有这项要求且画像里没有或明显不足；"
        "not_required：JD 里找不到这项要求（jd_source 为'无'）；"
        "already_has：画像已具备，或 JD 是多选一而画像已满足其中之一"
    )
    evidence: str = Field(description="一句话依据")


class GapJudgeResult(BaseModel):
    verdicts: list[GapVerdict] = Field(description="每条缺失技能一个判断，不能遗漏")


GAP_JUDGE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "你是严格的招聘评估核查员，只依据给定的岗位和候选人画像判断，不做任何推测。"),
    ("user", """岗位（结构化 JD）：
{job}

候选人画像：
{profile}

模型认为候选人缺失的技能（带序号）：
{items}

对每一条，先在 JD 的必需技能、加分技能、职责三处找对应原文填到 jd_source，再分类：
- valid：JD 有这项要求，且画像里没有或明显不足。注意：
  - 加分技能也是 JD 的要求，出现在加分技能里的算 valid。
  - 比 JD 说得更细或更具体也算 valid，例如 JD 写"落地RAG"、这里写"向量检索"；
    JD 写"大语言模型基本原理"、这里写"大模型训练/微调机制"。
  - 画像里只有相关但更浅的经验，也算 valid。
- already_has：画像里已经明确具备；或者 JD 是多选一（如"Java、Python 任一"），
  画像已满足其中之一，那么其余选项不算缺失。
- not_required：在 JD 三处都找不到对应要求，jd_source 填"无"。

每条单独判断，与其他条目是否重复不影响结论。index 与输入序号一一对应。"""),
])


@lru_cache
def gap_judge_chain():
    return GAP_JUDGE_PROMPT | get_model("judge").with_structured_output(GapJudgeResult)


def judge_gaps(profile: dict, job: dict, result: dict) -> list[dict]:
    """返回每条缺失技能的分类；裁判输出条数对不上时抛错，不静默丢数据。"""
    gaps = result.get("missing_skills") or []
    if not gaps:
        return []
    out = gap_judge_chain().invoke({
        "job": json.dumps(job, ensure_ascii=False, indent=2),
        "profile": json.dumps(profile, ensure_ascii=False, indent=2),
        "items": "\n".join(f"{i}. {g}" for i, g in enumerate(gaps)),
    })
    if out is None or sorted(v.index for v in out.verdicts) != list(range(len(gaps))):
        raise ValueError(f"裁判输出与 {len(gaps)} 条缺失技能对不上")
    return [_consistent({"text": gaps[v.index], **v.model_dump()}) for v in sorted(out.verdicts, key=lambda v: v.index)]


def _consistent(verdict: dict) -> dict:
    """一致性约束：摘录到了 JD 原文却判 not_required 是自相矛盾，按 valid 计并标记出来。"""
    if verdict["category"] == "not_required" and verdict["jd_source"].strip() not in ("", "无"):
        return {**verdict, "category": "valid", "corrected": True}
    return verdict
