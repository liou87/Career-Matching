"""AI 助手：写操作确认、长期记忆注入、SSE 接口、对话恢复。用假模型驱动，不调 LLM。"""
import json

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command

import app.agent.agent as agent_module
from app.agent.memory import NAMESPACE
from app.agent.persistence import open_persistence
from app.db import models


class ScriptedModel(GenericFakeChatModel):
    """按顺序返回预设消息的假模型，同时记下每次收到的输入，方便检查系统提示。"""

    seen: list = []

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, *args, **kwargs):
        self.seen.append(messages)
        return super()._generate(messages, *args, **kwargs)

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        # 自带的假模型流式时不支持工具调用，这里把整条消息作为一个流片段发出
        msg = self._generate(messages, stop=stop, run_manager=run_manager, **kwargs).generations[0].message
        yield ChatGenerationChunk(message=AIMessageChunk(
            content=msg.content,
            tool_call_chunks=[
                {"name": tc["name"], "args": json.dumps(tc["args"]), "id": tc["id"], "index": i}
                for i, tc in enumerate(msg.tool_calls)
            ],
        ))


@pytest.fixture
def script(monkeypatch):
    def install(*replies):
        model = ScriptedModel(messages=iter(replies), seen=[])
        monkeypatch.setattr(agent_module, "get_model", lambda role: model)
        return model

    return install


def _call(name, args, call_id="c1"):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


CHECKLIST_ARGS = {"items": [{"content": "补一个 RAG 项目", "importance": "高", "category": "action"}]}


def test_write_tool_waits_for_confirmation_then_runs(script, db):
    script(_call("add_to_checklist", CHECKLIST_ARGS), AIMessage(content="已加入清单"))
    agent = agent_module.build_agent(InMemorySaver(), InMemoryStore())
    config = {"configurable": {"thread_id": "t1"}}

    result = agent.invoke({"messages": [("user", "把补 RAG 项目加进清单")]}, config)

    action = result["__interrupt__"][0].value["action_requests"][0]
    assert action["name"] == "add_to_checklist"
    assert db.query(models.Checklist).count() == 0  # 确认之前没有写入

    agent.invoke(Command(resume={"decisions": [{"type": "approve"}]}), config)

    assert [c.content for c in db.query(models.Checklist).all()] == ["补一个 RAG 项目"]


def test_rejected_write_does_not_run(script, db):
    script(_call("add_to_checklist", CHECKLIST_ARGS), AIMessage(content="好的，不加了"))
    agent = agent_module.build_agent(InMemorySaver(), InMemoryStore())
    config = {"configurable": {"thread_id": "t1"}}

    agent.invoke({"messages": [("user", "把补 RAG 项目加进清单")]}, config)
    agent.invoke(Command(resume={"decisions": [{"type": "reject", "message": "先不加"}]}), config)

    assert db.query(models.Checklist).count() == 0


def test_saved_preferences_are_injected_into_system_prompt(script):
    model = script(AIMessage(content="你说过不考虑外包岗位"))
    store = InMemoryStore()
    store.put(NAMESPACE, "m1", {"content": "不考虑外包岗位"})
    agent = agent_module.build_agent(InMemorySaver(), store)

    agent.invoke({"messages": [("user", "我的偏好是什么？")]}, {"configurable": {"thread_id": "t1"}})

    system = model.seen[0][0].content
    assert "不考虑外包岗位" in system


def _events(response) -> list[dict]:
    return [json.loads(line[len("data: "):]) for line in response.text.splitlines() if line.startswith("data: ")]


def test_sse_chat_confirm_and_restore(script, client, db):
    script(_call("add_to_checklist", CHECKLIST_ARGS), AIMessage(content="已加入清单"))

    first = _events(client.post("/api/agent/chat", json={"message": "把补 RAG 项目加进清单"}))
    thread_id = first[0]["thread_id"]
    assert [e["type"] for e in first][0] == "thread"
    assert any(e["type"] == "tool_call" and e["name"] == "add_to_checklist" for e in first)
    assert any(e["type"] == "interrupt" for e in first)

    # 有待确认的操作时不能继续发消息
    blocked = _events(client.post("/api/agent/chat", json={"message": "你好", "thread_id": thread_id}))
    assert any(e["type"] == "error" and e["code"] == "CONFLICT" for e in blocked)

    restored = client.get(f"/api/agent/threads/{thread_id}").json()
    assert restored["pending"][0]["name"] == "add_to_checklist"

    done = _events(client.post("/api/agent/resume", json={"thread_id": thread_id, "approve": True}))
    assert "".join(e["text"] for e in done if e["type"] == "token").replace(" ", "") == "已加入清单"
    assert done[-1]["type"] == "done"
    assert db.query(models.Checklist).count() == 1
    assert client.get(f"/api/agent/threads/{thread_id}").json()["pending"] == []


def test_memories_can_be_listed_and_deleted(client):
    with open_persistence() as (_, store):
        store.put(NAMESPACE, "m1", {"content": "只看上海的岗位"})

    assert [m["content"] for m in client.get("/api/agent/memories").json()] == ["只看上海的岗位"]
    client.delete("/api/agent/memories/m1")
    assert client.get("/api/agent/memories").json() == []
