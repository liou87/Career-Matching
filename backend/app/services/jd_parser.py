"""
JD 解析：把粘贴的招聘原文解析成结构化字段。

用 with_structured_output 按 ParsedJD 校验输出，字段缺失或类型不对会直接
报错，不会把 LLM 多返回的字段原样塞进数据库模型。
"""
from functools import lru_cache

from langchain_core.prompts import ChatPromptTemplate

from app.core.errors import LLMOutputError
from app.llm.factory import get_model
from app.llm.schemas import ParsedJD

JD_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "你负责从招聘 JD 中提取结构化信息。只提取原文里有的内容，没有的字段留空，不要推测。"),
    ("user", "JD原文：\n{raw_jd}"),
])


@lru_cache
def jd_chain():
    return JD_PROMPT | get_model("jd_parse").with_structured_output(ParsedJD)


def parse_jd(raw_jd: str) -> dict:
    result = jd_chain().invoke({"raw_jd": raw_jd})
    if result is None:
        raise LLMOutputError("JD 解析没有返回结构化结果")
    return result.model_dump()
