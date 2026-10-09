"""LLM 调用日志：线上指标（耗时、token、成功率）的数据来源。"""
import logging

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from app.llm.callbacks import LLMCallLogger


class _Collector(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record):
        self.records.append(record)


@pytest.fixture
def records():
    # app 这一支 logger 不向 root 传播，caplog 收不到，直接挂一个收集器
    logger = logging.getLogger("app.llm.callbacks")
    collector = _Collector()
    logger.addHandler(collector)
    logger.setLevel(logging.INFO)
    yield collector.records
    logger.removeHandler(collector)


def test_logs_role_latency_and_tokens(records):
    reply = AIMessage(content="ok", usage_metadata={"input_tokens": 120, "output_tokens": 30, "total_tokens": 150})
    model = GenericFakeChatModel(messages=iter([reply]), callbacks=[LLMCallLogger("analysis", "fake-model")])

    model.invoke("hi")

    fields = records[-1].fields
    assert fields["role"] == "analysis" and fields["model"] == "fake-model"
    assert fields["ok"] is True
    assert (fields["input_tokens"], fields["output_tokens"]) == (120, 30)
    assert fields["ms"] is not None


def test_logs_failures(records):
    class FailingModel(GenericFakeChatModel):
        def _generate(self, *args, **kwargs):
            raise TimeoutError("upstream timeout")

    model = FailingModel(messages=iter([]), callbacks=[LLMCallLogger("merge", "fake-model")])

    with pytest.raises(TimeoutError):
        model.invoke("hi")

    fields = records[-1].fields
    assert fields["ok"] is False and "upstream timeout" in fields["error"]
