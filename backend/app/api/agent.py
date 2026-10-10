import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app import schemas
from app.agent import stream
from app.core.guard import ai_guard

router = APIRouter(prefix="/agent", tags=["agent"])

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


@router.post("/chat", dependencies=[Depends(ai_guard)])
def chat(data: schemas.AgentChatIn):
    """发一条消息，以 SSE 流式返回回答、工具调用和待确认的操作。"""
    thread_id = data.thread_id or uuid.uuid4().hex
    return StreamingResponse(stream.stream_chat(thread_id, data.message),
                             media_type="text/event-stream", headers=SSE_HEADERS)


@router.post("/resume", dependencies=[Depends(ai_guard)])
def resume(data: schemas.AgentResumeIn):
    """对待确认的写操作做出决定（确认或取消），继续以 SSE 流式返回。"""
    return StreamingResponse(stream.stream_resume(data.thread_id, data.approve, data.reason),
                             media_type="text/event-stream", headers=SSE_HEADERS)


@router.get("/threads/{thread_id}")
def get_thread(thread_id: str):
    """恢复对话历史和待确认的操作，刷新页面后用。"""
    return stream.get_thread(thread_id)


@router.get("/memories")
def list_memories():
    return stream.get_memories()


@router.delete("/memories/{memory_id}")
def delete_memory(memory_id: str):
    stream.delete_memory(memory_id)
    return {"ok": True}
