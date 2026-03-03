from __future__ import annotations

import os
import time
import uuid
from dataclasses import asdict
from typing import Any, Protocol

import boto3

from ..models.session import SessionState


class ConcurrencyError(RuntimeError):
    """Raised when a conditional update fails due to a stale version."""


class SessionRepository(Protocol):
    def create_session(self, session: SessionState) -> SessionState: ...

    def get_session(self, session_id: str) -> SessionState | None: ...

    def save_session(self, session: SessionState, *, expected_version: int) -> SessionState: ...


class DynamoDBSessionRepository:
    """DynamoDB-backed session repository.

    Table schema expectations:
      - PK: session_id (String)
      - TTL attribute: expires_at (Number, epoch seconds)
      - Version attribute: version (Number)
    """

    def __init__(self, table_name: str, ttl_seconds: int = 3600, table: Any | None = None) -> None:
        self._table = table or boto3.resource("dynamodb").Table(table_name)
        self._ttl_seconds = ttl_seconds

    def _expires_at(self) -> int:
        return int(time.time()) + self._ttl_seconds

    @staticmethod
    def _from_item(item: dict[str, Any]) -> SessionState:
        return SessionState(
            session_id=item["session_id"],
            required_functions=item.get("required_functions", []),
            target_account_id=item.get("target_account_id"),
            generated_policy_json=item.get("generated_policy_json"),
            magic_link_script=item.get("magic_link_script"),
            version=int(item.get("version", 0)),
            expires_at=int(item.get("expires_at", 0)) if item.get("expires_at") else None,
        )

    def create_session(self, session: SessionState) -> SessionState:
        now_with_ttl = self._expires_at()
        session.version = 1
        session.expires_at = now_with_ttl

        item = asdict(session)
        self._table.put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(session_id)",
        )
        return session

    def get_session(self, session_id: str) -> SessionState | None:
        response = self._table.get_item(Key={"session_id": session_id}, ConsistentRead=True)
        item = response.get("Item")
        if not item:
            return None
        return self._from_item(item)

    def save_session(self, session: SessionState, *, expected_version: int) -> SessionState:
        next_version = expected_version + 1
        expires_at = self._expires_at()
        try:
            self._table.update_item(
                Key={"session_id": session.session_id},
                UpdateExpression=(
                    "SET required_functions = :required_functions, "
                    "target_account_id = :target_account_id, "
                    "generated_policy_json = :generated_policy_json, "
                    "magic_link_script = :magic_link_script, "
                    "version = :next_version, "
                    "expires_at = :expires_at"
                ),
                ConditionExpression="version = :expected_version",
                ExpressionAttributeValues={
                    ":required_functions": session.required_functions,
                    ":target_account_id": session.target_account_id,
                    ":generated_policy_json": session.generated_policy_json,
                    ":magic_link_script": session.magic_link_script,
                    ":expected_version": expected_version,
                    ":next_version": next_version,
                    ":expires_at": expires_at,
                },
            )
        except Exception as exc:
            error_code = getattr(exc, "response", {}).get("Error", {}).get("Code")
            if error_code == "ConditionalCheckFailedException":
                raise ConcurrencyError("Session update conflict detected") from exc
            raise

        session.version = next_version
        session.expires_at = expires_at
        return session


class SessionService:
    def __init__(self, repository: SessionRepository) -> None:
        self._repository = repository

    @classmethod
    def from_env(cls) -> "SessionService":
        table_name = os.getenv("SESSION_TABLE_NAME", "agentic-magic-link-sessions")
        ttl_seconds = int(os.getenv("SESSION_TTL_SECONDS", "3600"))
        return cls(DynamoDBSessionRepository(table_name=table_name, ttl_seconds=ttl_seconds))

    def create_session(self) -> SessionState:
        session = SessionState(session_id=str(uuid.uuid4()))
        return self._repository.create_session(session)

    def get_session(self, session_id: str) -> SessionState | None:
        return self._repository.get_session(session_id)

    def update_from_message(self, session_id: str, user_message: str) -> SessionState:
        session = self._repository.get_session(session_id)
        if session is None:
            raise KeyError(session_id)

        original_version = session.version

        if "required_functions" in user_message.lower():
            session.required_functions = [item.strip() for item in user_message.split(",") if item.strip()]

        if "target account" in user_message.lower():
            tokens = user_message.split()
            maybe_account_id = next((token for token in tokens if token.isdigit() and len(token) == 12), None)
            if maybe_account_id:
                session.target_account_id = maybe_account_id

        if "policy" in user_message.lower():
            session.generated_policy_json = '{"Version":"2012-10-17","Statement":[]}'

        if "script" in user_message.lower() or "magic link" in user_message.lower():
            session.magic_link_script = "#!/usr/bin/env bash\necho 'Generate magic link flow'"

        return self._repository.save_session(session, expected_version=original_version)
