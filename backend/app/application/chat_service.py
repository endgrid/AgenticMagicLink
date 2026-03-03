from backend.app.models.chat import (
    ChatMessage,
    MagicLinkScriptPayload,
    MessageRequest,
    MessageResponse,
    SessionResponse,
)
from backend.app.services.session_store import SessionStore


class SessionNotFoundError(Exception):
    """Raised when message handling is attempted for an unknown session."""


def create_session_response(store: SessionStore) -> SessionResponse:
    session = store.create_session()
    next_expected_input = "work_description"
    return SessionResponse(
        session_id=session.session_id,
        initial_assistant_message=build_initial_assistant_message(),
        next_expected_input=next_expected_input,
    )


def build_initial_assistant_message() -> str:
    return (
        "Please describe the IAM workflow or AWS functions you want this magic "
        "link flow to support."
    )


def _determine_next_expected_input(
    required_functions: list[str],
    target_account_id: str | None,
    role_arn: str | None,
    session_duration_seconds: int | None,
) -> str | None:
    if not required_functions:
        return "work_description"
    if not target_account_id:
        return "account_id"
    if not role_arn:
        return "role_arn"
    if not session_duration_seconds:
        return "session_duration"
    return None


def _build_assistant_prompt(
    required_functions: list[str],
    target_account_id: str | None,
    role_arn: str | None,
    session_duration_seconds: int | None,
    generated_policy_json: str | None,
    magic_link_script: str | None,
    workflow_message: str | None,
    next_expected_input: str | None,
) -> str:
    prompt_by_stage = {
        "work_description": (
            build_initial_assistant_message()
        ),
        "account_id": "Great. Next, provide the 12-digit AWS account ID this flow should target.",
        "role_arn": (
            "Thanks. Now provide the IAM role ARN to assume "
            "(example: arn:aws:iam::123456789012:role/MyRole)."
        ),
        "session_duration": (
            "Great. Choose a session duration in seconds for the contractor session. "
            "Allowed range is 900 to 43200 seconds."
        ),
        None: (
            "All required inputs are captured. You can ask for policy/script generation "
            "refinements or request another script version."
        ),
    }

    assistant_guidance = prompt_by_stage[next_expected_input]
    if workflow_message:
        assistant_guidance = f"{assistant_guidance}\n\n{workflow_message}"

    return (
        "Captured workflow state:\n"
        f"- required_functions: {required_functions or 'unset'}\n"
        f"- target_account_id: {target_account_id or 'unset'}\n"
        f"- role_arn: {role_arn or 'unset'}\n"
        f"- session_duration_seconds: {session_duration_seconds or 'unset'}\n"
        f"- generated_policy_json: {'set' if generated_policy_json else 'unset'}\n"
        f"- magic_link_script: {'set' if magic_link_script else 'unset'}\n\n"
        f"{assistant_guidance}"
    )


def build_message_response(payload: MessageRequest, store: SessionStore) -> MessageResponse:
    session = store.get_session(payload.session_id)
    if not session:
        raise SessionNotFoundError(payload.session_id)

    updated_session = store.update_from_message(payload.session_id, payload.message)
    next_expected_input = _determine_next_expected_input(
        updated_session.required_functions,
        updated_session.target_account_id,
        updated_session.role_arn,
        updated_session.session_duration_seconds,
    )

    assistant_text = _build_assistant_prompt(
        updated_session.required_functions,
        updated_session.target_account_id,
        updated_session.role_arn,
        updated_session.session_duration_seconds,
        updated_session.generated_policy_json,
        updated_session.magic_link_script,
        updated_session.workflow_message,
        next_expected_input,
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
        next_expected_input=next_expected_input,
    )
