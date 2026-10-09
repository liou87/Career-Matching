"""
AI 助手的对话服务：把 agent 的运行过程转成前端消费的事件流（SSE），
以及恢复对话历史、管理长期偏好。

事件类型：
- thread：本轮所属的对话 id（第一个事件）
- token：回答的一段文字
- tool_call：助手发起了一次工具调用（name、args）
- tool_result：工具执行完成（name）
- interrupt：有写操作等待用户确认（actions：name、args、description）
- done：本轮结束（thread_id）
- error：出错（detail、code）
"""
import json
import logging
from collections.abc import Iterator

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from langchain_core.tracers.langchain import wait_for_all_tracers
from langgraph.types import Command

from app.agent.agent import build_agent
from app.agent.memory import NAMESPACE, list_memories
from app.agent.persistence import open_persistence
from app.core.config import settings
from app.core.errors import ConflictError, classify

logger = logging.getLogger(__name__)


def _config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def _pending_actions(agent, thread_id: str) -> list[dict]:
    state = agent.get_state(_config(thread_id))
    actions = []
    for it in state.interrupts or ():
        actions.extend((it.value or {}).get("action_requests", []))
    return actions


def stream_chat(thread_id: str, message: str) -> Iterator[str]:
    """用户发一条新消息。有待确认的操作时拒绝，避免对话状态里留下没有结果的工具调用。"""
    def run(agent):
        if _pending_actions(agent, thread_id):
            raise ConflictError("有一个操作在等你确认，请先确认或取消")
        return {"messages": [HumanMessage(content=message)]}

    return _stream(thread_id, run)


def stream_resume(thread_id: str, approve: bool, reason: str | None = None) -> Iterator[str]:
    """用户对待确认的操作做出决定后继续执行。"""
    def run(agent):
        actions = _pending_actions(agent, thread_id)
        if not actions:
            raise ConflictError("没有等待确认的操作")
        decision = {"type": "approve"} if approve else {"type": "reject", "message": reason or "用户取消了这个操作"}
        return Command(resume={"decisions": [decision] * len(actions)})

    return _stream(thread_id, run)


def _stream(thread_id: str, make_input) -> Iterator[str]:
    yield _sse({"type": "thread", "thread_id": thread_id})
    try:
        with open_persistence() as (saver, store):
            agent = build_agent(saver, store)
            payload = make_input(agent)
            for mode, chunk in agent.stream(payload, _config(thread_id), stream_mode=["messages", "updates"]):
                for event in _events(mode, chunk):
                    yield _sse(event)
        yield _sse({"type": "done", "thread_id": thread_id})
    except Exception as e:  # noqa: BLE001  流已经开始，错误只能作为事件发给前端
        status, code, message = classify(e)
        if status >= 500:
            logger.exception("agent_stream_failed")
        yield _sse({"type": "error", "code": code, "detail": message})
    finally:
        # 流式响应在请求中间件结束之后才发完，trace 要在这里等它上传完
        if settings.langsmith_tracing:
            wait_for_all_tracers()


def _events(mode: str, chunk) -> Iterator[dict]:
    if mode == "messages":
        msg, meta = chunk
        # 只转发主模型节点的文字；摘要中间件里的模型调用不推给前端
        if meta.get("langgraph_node") == "model" and isinstance(msg, AIMessageChunk) and msg.content:
            yield {"type": "token", "text": msg.content}
        return
    for node, update in chunk.items():
        if node == "__interrupt__":
            actions = [a for it in update for a in (it.value or {}).get("action_requests", [])]
            yield {"type": "interrupt", "actions": actions}
            continue
        for m in (update or {}).get("messages", []) if isinstance(update, dict) else []:
            if isinstance(m, AIMessage):
                for tc in m.tool_calls:
                    yield {"type": "tool_call", "name": tc["name"], "args": tc["args"]}
            elif isinstance(m, ToolMessage):
                yield {"type": "tool_result", "name": m.name}


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def get_thread(thread_id: str) -> dict:
    """恢复对话：返回可展示的消息和等待确认的操作。"""
    with open_persistence() as (saver, store):
        agent = build_agent(saver, store)
        state = agent.get_state(_config(thread_id))
        messages = []
        for m in (state.values or {}).get("messages", []):
            if isinstance(m, HumanMessage):
                messages.append({"role": "user", "content": m.content})
            elif isinstance(m, AIMessage):
                tools = [tc["name"] for tc in m.tool_calls]
                if messages and messages[-1]["role"] == "assistant" and not messages[-1]["content"]:
                    messages[-1]["tool_calls"] += tools
                    messages[-1]["content"] = m.content
                else:
                    messages.append({"role": "assistant", "content": m.content, "tool_calls": tools})
        pending = [a for it in state.interrupts or () for a in (it.value or {}).get("action_requests", [])]
        return {"thread_id": thread_id, "messages": messages, "pending": pending}


def get_memories() -> list[dict]:
    with open_persistence() as (_, store):
        return list_memories(store)


def delete_memory(memory_id: str) -> None:
    with open_persistence() as (_, store):
        store.delete(NAMESPACE, memory_id)
