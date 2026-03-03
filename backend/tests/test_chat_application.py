import json

from backend.app.application.chat_service import (
    SessionNotFoundError,
    build_initial_assistant_message,
    build_message_response,
    create_session_response,
)
from backend.app.lambda_handlers.chat import post_message_handler
from backend.app.models.chat import ChatMessage, MessageRequest
from backend.app.services.session_store import InMemorySessionStore


def test_create_session_response_returns_session_id():
    store = InMemorySessionStore()

    response = create_session_response(store)

    assert response.session_id
    assert response.initial_assistant_message == build_initial_assistant_message()
    assert response.next_expected_input == "work_description"
    assert store.get_session(response.session_id) is not None


def test_build_message_response_appends_messages():
    store = InMemorySessionStore()
    session_id = create_session_response(store).session_id
    payload = MessageRequest(
        session_id=session_id,
        message="Please capture required_functions, createUser, deleteUser",
        history=[ChatMessage(role="assistant", content="hello")],
    )

    response = build_message_response(payload, store)

    assert response.session_id == session_id
    assert len(response.messages) == 3
    assert response.messages[-1].role == "assistant"


def test_build_message_response_walks_stage_to_script_payload():
    store = InMemorySessionStore()
    session_id = create_session_response(store).session_id

    build_message_response(
        MessageRequest(session_id=session_id, message="required_functions, listBuckets"),
        store,
    )
    account_payload = MessageRequest(session_id=session_id, message="Target account is 123456789012")
    account_response = build_message_response(account_payload, store)
    assert "Create the contractor role in AWS" in account_response.messages[-1].content
    assert account_response.magic_link_script is None

    role_payload = MessageRequest(
        session_id=session_id,
        message="Use role arn:aws:iam::123456789012:role/ContractorRole",
        history=account_response.messages,
    )
    role_response = build_message_response(role_payload, store)
    assert role_response.magic_link_script is None
    assert role_response.next_expected_input == "session_duration"

    duration_response = build_message_response(
        MessageRequest(
            session_id=session_id,
            message="Set duration to 1800 seconds",
            history=role_response.messages,
        ),
        store,
    )

    assert duration_response.magic_link_script is not None
    assert "Run instructions:" in duration_response.messages[-1].content


def test_build_message_response_raises_for_missing_session():
    store = InMemorySessionStore()
    payload = MessageRequest(session_id="missing", message="hello")

    try:
        build_message_response(payload, store)
        raise AssertionError("Expected SessionNotFoundError")
    except SessionNotFoundError:
        pass


def test_lambda_post_message_returns_404_for_missing_session():
    event = {
        "body": json.dumps(
            {
                "session_id": "missing",
                "message": "hello",
                "history": [],
            }
        )
    }

    response = post_message_handler(event, None)

    assert response["statusCode"] == 404
    assert json.loads(response["body"]) == {"detail": "Session not found"}


def test_build_message_response_sets_next_expected_input_stage():
    store = InMemorySessionStore()
    session_id = create_session_response(store).session_id

    response = build_message_response(
        MessageRequest(session_id=session_id, message='Need required_functions, listBuckets, getObject'),
        store,
    )

    assert response.next_expected_input == 'account_id'
    assert '12-digit AWS account ID' in response.messages[-1].content




def test_build_message_response_captures_role_arn_and_moves_to_duration_stage():
    store = InMemorySessionStore()
    session_id = create_session_response(store).session_id

    build_message_response(
        MessageRequest(session_id=session_id, message='required_functions, listBuckets'),
        store,
    )
    build_message_response(
        MessageRequest(session_id=session_id, message='target account 123456789012'),
        store,
    )
    response = build_message_response(
        MessageRequest(
            session_id=session_id,
            message='use arn:aws:iam::123456789012:role/AgenticMagicLinkRole',
        ),
        store,
    )

    assert response.next_expected_input == "session_duration"
    assert "Allowed range is 900 to 43200 seconds" in response.messages[-1].content
