import json

from backend.app.application.chat_service import SessionNotFoundError, build_message_response, create_session_response
from backend.app.lambda_handlers.chat import post_message_handler
from backend.app.models.chat import ChatMessage, MessageRequest
from backend.app.services.session_store import InMemorySessionStore


def test_create_session_response_returns_session_id():
    store = InMemorySessionStore()

    response = create_session_response(store)

    assert response.session_id
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


def test_prompt_flow_requests_account_then_role_then_returns_script():
    store = InMemorySessionStore()
    session_id = create_session_response(store).session_id

    first_response = build_message_response(
        MessageRequest(
            session_id=session_id,
            message="required_functions, ec2:DescribeInstances, s3:ListBucket",
        ),
        store,
    )

    assert "AWS account ID" in first_response.messages[-1].content
    assert first_response.magic_link_script is None

    second_response = build_message_response(
        MessageRequest(
            session_id=session_id,
            message="My target account is 123456789012",
            history=first_response.messages,
        ),
        store,
    )

    assert "IAM role" in second_response.messages[-1].content
    assert second_response.magic_link_script is None

    final_response = build_message_response(
        MessageRequest(
            session_id=session_id,
            message="Role ARN: arn:aws:iam::123456789012:role/MagicLinkRole",
            history=second_response.messages,
        ),
        store,
    )

    assert "generated your magic-link script payload" in final_response.messages[-1].content
    assert final_response.magic_link_script is not None
