import json
import os
from typing import Any

from pydantic import ValidationError

from backend.app.application.chat_service import (
    SessionNotFoundError,
    build_message_response,
    create_session_response,
)
from backend.app.models.chat import MessageRequest
from backend.app.services.session_store import DynamoDBSessionStore, InMemorySessionStore


JsonDict = dict[str, Any]


def _build_store() -> InMemorySessionStore | DynamoDBSessionStore:
    table_name = os.getenv("SESSION_TABLE_NAME")
    if table_name:
        return DynamoDBSessionStore(table_name=table_name)
    return InMemorySessionStore()


store = _build_store()


def _response(status_code: int, body: JsonDict) -> JsonDict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def post_session_handler(event: JsonDict, context: Any) -> JsonDict:  # noqa: ARG001
    session_response = create_session_response(store)
    return _response(200, session_response.model_dump())


def post_message_handler(event: JsonDict, context: Any) -> JsonDict:  # noqa: ARG001
    raw_body = event.get("body") or "{}"

    try:
        payload_dict = json.loads(raw_body)
    except json.JSONDecodeError:
        return _response(400, {"detail": "Invalid JSON body"})

    try:
        payload = MessageRequest.model_validate(payload_dict)
    except ValidationError as exc:
        return _response(422, {"detail": exc.errors()})

    try:
        message_response = build_message_response(payload, store)
    except SessionNotFoundError:
        return _response(404, {"detail": "Session not found"})

    return _response(200, message_response.model_dump())
