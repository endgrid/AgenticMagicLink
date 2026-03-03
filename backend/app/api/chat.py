from fastapi import APIRouter, HTTPException

from app.models.chat import (
    ChatMessage,
    MagicLinkScriptPayload,
    MessageRequest,
    MessageResponse,
    SessionResponse,
)
from app.services.session_store import InMemorySessionStore

router = APIRouter(prefix="/api/chat", tags=["chat"])
store = SessionService.from_env()


@router.post("/session", response_model=SessionResponse)
def create_session() -> SessionResponse:
    return create_session_response(store)


@router.post("/message", response_model=MessageResponse)
def chat_message(payload: MessageRequest) -> MessageResponse:
    session = store.get_session(payload.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        updated_session = store.update_from_message(payload.session_id, payload.message)
    except ConcurrencyError as exc:
        raise HTTPException(status_code=409, detail="Session update conflict, retry request") from exc

    assistant_text = (
        "Captured workflow state:\n"
        f"- required_functions: {updated_session.required_functions or '[]'}\n"
        f"- target_account_id: {updated_session.target_account_id or 'unset'}\n"
        f"- generated_policy_json: {'set' if updated_session.generated_policy_json else 'unset'}\n"
        f"- magic_link_script: {'set' if updated_session.magic_link_script else 'unset'}"
    )

    messages = [
        *payload.history,
        ChatMessage(role="user", content=payload.message),
        ChatMessage(role="assistant", content=assistant_text),
    ]

    magic_link_script_payload = None
    if updated_session.magic_link_script:
        magic_link_script_payload = MagicLinkScriptPayload(
            content=updated_session.magic_link_script,
            checksum_sha256=updated_session.magic_link_script_checksum_sha256,
            version=updated_session.magic_link_script_version,
        )

    return MessageResponse(
        session_id=payload.session_id,
        messages=messages,
        magic_link_script=magic_link_script_payload,
    )
