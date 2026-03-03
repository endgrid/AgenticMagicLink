from __future__ import annotations

from unittest.mock import Mock

import pytest

from backend.app.models.session import SessionState
from backend.app.services.session_store import ConcurrencyError, DynamoDBSessionRepository, SessionService


class StubRepository:
    def __init__(self) -> None:
        self.session = SessionState(session_id="session-1", version=2)

    def create_session(self, session: SessionState) -> SessionState:
        return session

    def get_session(self, session_id: str) -> SessionState | None:
        return self.session if session_id == self.session.session_id else None

    def save_session(self, session: SessionState, *, expected_version: int) -> SessionState:
        assert expected_version == 2
        session.version = 3
        return session


def test_session_service_updates_and_persists() -> None:
    service = SessionService(StubRepository())

    updated = service.update_from_message(
        "session-1",
        "required_functions,lambda:InvokeFunction target account 123456789012 policy script",
    )

    assert updated.required_functions
    assert updated.target_account_id == "123456789012"
    assert updated.generated_policy_json is not None
    assert updated.magic_link_script is not None
    assert updated.version == 3


def test_dynamodb_save_session_raises_concurrency_error() -> None:
    table = Mock()
    repo = DynamoDBSessionRepository(table_name="sessions", table=table)

    class ConditionalFailure(Exception):
        def __init__(self) -> None:
            self.response = {"Error": {"Code": "ConditionalCheckFailedException"}}

    table.update_item.side_effect = ConditionalFailure()

    with pytest.raises(ConcurrencyError):
        repo.save_session(SessionState(session_id="session-1"), expected_version=1)
