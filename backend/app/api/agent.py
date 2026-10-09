from fastapi import APIRouter
from app import schemas
from app.agent.job_agent import chat

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/chat", response_model=schemas.AgentChatOut)
def agent_chat(data: schemas.AgentChatIn):
    history = [h.model_dump() for h in data.history]
    return chat(data.message, history)
