from backend.app.models.chat import (
    ChatMessage,
    MagicLinkScriptPayload,
    MessageRequest,
    MessageResponse,
    SessionResponse,
)
from backend.app.services.session_store import InMemorySessionStore


class SessionNotFoundError(Exception):
    """Raised when message handling is attempted for an unknown session."""


def create_session_response(store: InMemorySessionStore) -> SessionResponse:
    session = store.create_session()
    return SessionResponse(session_id=session.session_id)


def build_message_response(payload: MessageRequest, store: InMemorySessionStore) -> MessageResponse:
    session = store.get_session(payload.session_id)
    if not session:
        raise SessionNotFoundError(payload.session_id)

    updated_session = store.update_from_message(payload.session_id, payload.message)

    assistant_text = (
        updated_session.next_assistant_prompt
        or "I updated the session state. Please continue with the next setup detail."
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
