import pytest

from app.core.errors import LLMOutputError
from app.llm.schemas import ParsedJD
from app.services import jd_parser
from tests.fakes import FakeChain


def test_parse_jd_returns_only_known_fields(monkeypatch):
    # LLM 多返回的字段会被 Pydantic 丢掉，不会原样塞进数据库模型导致报错
    parsed = ParsedJD.model_validate({"title": "AI 工程师", "company": "某公司", "unexpected_field": 1})
    monkeypatch.setattr(jd_parser, "jd_chain", lambda: FakeChain(parsed))

    result = jd_parser.parse_jd("JD 原文")

    assert result["title"] == "AI 工程师"
    assert "unexpected_field" not in result
    assert result["required_skills"] == []


def test_parse_jd_raises_on_empty_output(monkeypatch):
    monkeypatch.setattr(jd_parser, "jd_chain", lambda: FakeChain(None))

    with pytest.raises(LLMOutputError):
        jd_parser.parse_jd("JD 原文")
