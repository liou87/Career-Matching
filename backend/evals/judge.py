"""
编造检测：用更强的裁判模型（settings.model_judge）逐条检查建议，
判断它有没有把画像里不存在的经历、项目、技能当作候选人已有的。

「建议去做一件事」不算编造，只有「把没有的东西说成已有」才算。
LLM 当裁判有误判的可能，结论只用于版本间的相对比较，见 docs/evals.md。
"""
import json
from functools import lru_cache

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
