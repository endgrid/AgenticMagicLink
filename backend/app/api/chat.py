from fastapi import APIRouter, HTTPException

from backend.app.application.chat_service import (
    SessionNotFoundError,
    build_message_response,
    create_session_response,
)
from backend.app.models.chat import MessageRequest, MessageResponse, SessionResponse
from backend.app.services.session_store import InMemorySessionStore

router = APIRouter(prefix="/api/chat", tags=["chat"])
store = InMemorySessionStore()


@router.post("/session", response_model=SessionResponse)
def create_session() -> SessionResponse:
    return create_session_response(store)


@router.post("/message", response_model=MessageResponse)
def chat_message(payload: MessageRequest) -> MessageResponse:
    try:
        return build_message_response(payload, store)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc
