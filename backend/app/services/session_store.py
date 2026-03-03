from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
import uuid
from dataclasses import asdict
from decimal import Decimal
from typing import Protocol

import boto3

from src.bedrock_client import (
    BedrockClient,
    BedrockConfigurationError,
    BedrockInvocationError,
    BedrockOutputError,
)
from src.magic_link_script import (
    MAGIC_LINK_SCRIPT_VERSION,
    MAX_SESSION_DURATION_SECONDS,
    MIN_SESSION_DURATION_SECONDS,
    MagicLinkScriptConfig,
    generate_magic_link_script,
)

from ..models.session import SessionState

logger = logging.getLogger(__name__)

ACCOUNT_ID_PATTERN = re.compile(r"\b(\d{12})\b")
ROLE_ARN_PATTERN = re.compile(r"\barn:aws:iam::(\d{12}):role\/[A-Za-z0-9+=,.@_\/-]{1,512}\b")


class PolicyFailureDLQ:
    def __init__(self, queue_url: str | None = None, sqs_client: object | None = None) -> None:
        self.queue_url = queue_url if queue_url is not None else os.getenv("POLICY_FAILURE_DLQ_URL")
        self._sqs_client = sqs_client

    def enqueue(self, payload: dict[str, object]) -> None:
        if not self.queue_url:
            return

        sqs_client = self._sqs_client or boto3.client("sqs")
        sqs_client.send_message(QueueUrl=self.queue_url, MessageBody=json.dumps(payload))


class SessionStore(Protocol):
    def create_session(self) -> SessionState: ...

    def get_session(self, session_id: str) -> SessionState | None: ...

    def update_from_message(self, session_id: str, user_message: str) -> SessionState: ...


class InMemorySessionStore:
    def __init__(
        self,
        *,
        bedrock_client: BedrockClient | None = None,
        failure_dlq: PolicyFailureDLQ | None = None,
    ) -> None:
        self._sessions: dict[str, SessionState] = {}
        self._bedrock_client = bedrock_client
        self._failure_dlq = failure_dlq or PolicyFailureDLQ()

    def create_session(self) -> SessionState:
        session = SessionState(
            session_id=str(uuid.uuid4()),
            conversation_stage="awaiting_work_description",
        )
        self._sessions[session.session_id] = session
        return session

    def get_session(self, session_id: str) -> SessionState | None:
        return self._sessions.get(session_id)

    def update_from_message(self, session_id: str, user_message: str) -> SessionState:
        session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(session_id)

        session.workflow_message = None
        lowered_message = user_message.lower()
        stripped_message = user_message.strip()

        maybe_account_id = self._extract_account_id(user_message)
        maybe_role_arn = self._extract_role_arn(user_message)

        if (
            not session.required_functions
            and stripped_message
            and not maybe_account_id
            and not maybe_role_arn
            and not self._looks_like_duration_input(user_message)
        ):
            session.required_functions = [
                item.strip()
                for item in re.split(r"[\n,]", user_message)
                if item.strip()
            ]

        if "required_functions" in lowered_message:
            session.required_functions = [
                item.strip() for item in user_message.split(",") if item.strip()
            ]
        elif not session.required_functions and user_message.strip():
            # Accept plain-language work descriptions even without the
            # `required_functions` keyword so the workflow can continue.
            session.required_functions = [user_message.strip()]

        if "target account" in lowered_message or "account id" in lowered_message or "account" in lowered_message:
            maybe_account_id = self._extract_account_id(user_message)
            if maybe_account_id:
                session.target_account_id = maybe_account_id
                session.workflow_message = (
                    "Create the contractor role in AWS, then send me the role ARN."
                )

        if maybe_account_id and not session.target_account_id:
            session.target_account_id = maybe_account_id

        if maybe_role_arn:
            session.role_arn = maybe_role_arn
            session.workflow_message = (
                "Got it. Now choose a session duration in seconds "
                f"between {MIN_SESSION_DURATION_SECONDS} and {MAX_SESSION_DURATION_SECONDS}."
            )
        elif "role" in lowered_message and "arn" in lowered_message:
            session.workflow_message = (
                "I couldn't validate that role ARN. Please send a full IAM role ARN, "
                "for example arn:aws:iam::123456789012:role/ContractorRole."
            )

        if session.role_arn:
            maybe_duration_seconds = self._extract_duration_seconds(user_message)
            if maybe_duration_seconds is not None:
                if MIN_SESSION_DURATION_SECONDS <= maybe_duration_seconds <= MAX_SESSION_DURATION_SECONDS:
                    session.session_duration_seconds = maybe_duration_seconds
                else:
                    session.workflow_message = (
                        "Session duration must be between "
                        f"{MIN_SESSION_DURATION_SECONDS} and {MAX_SESSION_DURATION_SECONDS} seconds."
                    )

        if "policy" in lowered_message:
            policy = self._generate_policy(session, user_message)
            session.generated_policy_json = json.dumps(policy) if policy else None

        if (
            session.target_account_id
            and session.role_arn
            and session.session_duration_seconds
            and (
                "script" in lowered_message
                or "magic link" in lowered_message
                or session.magic_link_script is None
            )
        ):
            self._build_magic_link_script(session)

        return session

    def _extract_account_id(self, user_message: str) -> str | None:
        match = re.search(r"\b(\d{12})\b", user_message)
        if match:
            return match.group(1)
        return None

    def _extract_role_arn(self, user_message: str) -> str | None:
        match = re.search(r"\barn:aws:iam::\d{12}:role/[A-Za-z0-9+=,.@_\-/]+\b", user_message)
        if match:
            return match.group(0)
        return None

    def _extract_duration_seconds(self, user_message: str) -> int | None:
        lowered_message = user_message.lower()
        if "duration" not in lowered_message and "second" not in lowered_message:
            return None

        match = re.search(r"\b(\d{3,5})\b", user_message)
        if not match:
            return None
        return int(match.group(1))

    def _looks_like_duration_input(self, user_message: str) -> bool:
        lowered_message = user_message.lower()
        stripped_message = user_message.strip()
        if not stripped_message:
            return False

        if re.fullmatch(r"\d{3,5}", stripped_message):
            return True

        has_duration_cue = "duration" in lowered_message or "seconds" in lowered_message
        has_duration_number = re.search(r"\b\d{3,5}\b", user_message) is not None
        return has_duration_cue and has_duration_number

    def _emit_metric(self, metric_name: str, value: int, outcome: str) -> None:
        metric_log = {
            "_aws": {
                "Timestamp": int(time.time() * 1000),
                "CloudWatchMetrics": [
                    {
                        "Namespace": "AgenticMagicLink/PolicyGeneration",
                        "Dimensions": [["Outcome"]],
                        "Metrics": [{"Name": metric_name, "Unit": "Count"}],
                    }
                ],
            },
            "Outcome": outcome,
            metric_name: value,
        }
        logger.info(json.dumps(metric_log))

    def _build_functions_text(self, session: SessionState, user_message: str) -> str:
        if session.required_functions:
            return "\n".join(f"- {fn}" for fn in session.required_functions)
        return user_message

    def _get_bedrock_client(self) -> BedrockClient:
        if self._bedrock_client is None:
            max_attempts = int(os.getenv("BEDROCK_MAX_ATTEMPTS", "2"))
            self._bedrock_client = BedrockClient.from_env(max_attempts=max_attempts)
        return self._bedrock_client

    def _generate_policy(
        self,
        session: SessionState,
        user_message: str,
    ) -> dict[str, object] | None:
        functions_text = self._build_functions_text(session, user_message)
        client = self._get_bedrock_client()

        try:
            policy = client.generate_policy_from_functions(functions_text)
            retry_count = max(client.last_attempts_used - 1, 0)
            logger.info(
                json.dumps(
                    {
                        "event": "policy_generation",
                        "status": "success",
                        "session_id": session.session_id,
                        "max_attempts": client.max_attempts,
                        "retries": retry_count,
                    }
                )
            )
            self._emit_metric("PolicyGenerationSuccess", 1, "success")
            if retry_count > 0:
                self._emit_metric("PolicyGenerationRetries", retry_count, "success")
            return policy
        except BedrockOutputError as exc:
            logger.warning(
                json.dumps(
                    {
                        "event": "policy_generation",
                        "status": "validation_failure",
                        "session_id": session.session_id,
                        "error": str(exc),
                    }
                )
            )
            self._emit_metric("PolicyValidationFailure", 1, "validation_failure")
            self._enqueue_failure(session, user_message, "validation_failure", str(exc))
        except BedrockInvocationError as exc:
            logger.error(
                json.dumps(
                    {
                        "event": "policy_generation",
                        "status": "invocation_failed_after_retries",
                        "session_id": session.session_id,
                        "retries": max(client.max_attempts - 1, 0),
                        "error": str(exc),
                    }
                )
            )
            self._emit_metric("PolicyInvocationRetryExhausted", 1, "retry_exhausted")
            self._enqueue_failure(session, user_message, "retry_exhausted", str(exc))
        except BedrockConfigurationError as exc:
            logger.error(
                json.dumps(
                    {
                        "event": "policy_generation",
                        "status": "configuration_error",
                        "session_id": session.session_id,
                        "error": str(exc),
                    }
                )
            )
            self._emit_metric("PolicyGenerationConfigurationError", 1, "configuration_error")

        return None

    def _enqueue_failure(
        self,
        session: SessionState,
        user_message: str,
        failure_type: str,
        error: str,
    ) -> None:
        try:
            self._failure_dlq.enqueue(
                {
                    "session_id": session.session_id,
                    "target_account_id": session.target_account_id,
                    "required_functions": session.required_functions,
                    "user_message": user_message,
                    "failure_type": failure_type,
                    "error": error,
                }
            )
            logger.info(
                json.dumps(
                    {
                        "event": "policy_generation_dlq",
                        "status": "enqueued",
                        "session_id": session.session_id,
                        "failure_type": failure_type,
                    }
                )
            )
            self._emit_metric("PolicyGenerationDLQEnqueue", 1, failure_type)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.exception(
                json.dumps(
                    {
                        "event": "policy_generation_dlq",
                        "status": "enqueue_failed",
                        "session_id": session.session_id,
                        "failure_type": failure_type,
                        "error": str(exc),
                    }
                )
            )

    def _build_magic_link_script(self, session: SessionState) -> None:
        config = MagicLinkScriptConfig(
            default_role_arn=session.role_arn or MagicLinkScriptConfig().default_role_arn,
            default_session_duration_seconds=(
                session.session_duration_seconds
                or MagicLinkScriptConfig().default_session_duration_seconds
            ),
            expected_account_id=session.target_account_id,
        )
        script = generate_magic_link_script(config)

        session.magic_link_script = script
        session.magic_link_script_checksum_sha256 = hashlib.sha256(
            script.encode("utf-8")
        ).hexdigest()
        session.magic_link_script_version = MAGIC_LINK_SCRIPT_VERSION
        session.workflow_message = (
            "Run instructions:\n"
            "1) Save the generated script to a local file.\n"
            "2) Execute with python and provide region/session options as needed."
        )


class DynamoDBSessionStore(InMemorySessionStore):
    def __init__(
        self,
        table_name: str,
        *,
        bedrock_client: BedrockClient | None = None,
        failure_dlq: PolicyFailureDLQ | None = None,
        dynamodb_resource: object | None = None,
    ) -> None:
        super().__init__(bedrock_client=bedrock_client, failure_dlq=failure_dlq)
        resource = dynamodb_resource or boto3.resource("dynamodb")
        self._table = resource.Table(table_name)

    def create_session(self) -> SessionState:
        session = SessionState(
            session_id=str(uuid.uuid4()),
            conversation_stage="awaiting_work_description",
        )
        self._table.put_item(Item=self._serialize_session(session))
        return session

    def get_session(self, session_id: str) -> SessionState | None:
        response = self._table.get_item(Key={"session_id": session_id})
        item = response.get("Item")
        if not item:
            return None
        return self._deserialize_session(item)

    def update_from_message(self, session_id: str, user_message: str) -> SessionState:
        session = self.get_session(session_id)
        if session is None:
            raise KeyError(session_id)

        self._sessions[session_id] = session
        updated = super().update_from_message(session_id, user_message)
        self._table.put_item(Item=self._serialize_session(updated))
        return updated

    def _serialize_session(self, session: SessionState) -> dict[str, object]:
        return asdict(session)

    def _deserialize_session(self, item: dict[str, object]) -> SessionState:
        if isinstance(item.get("session_duration_seconds"), Decimal):
            item = dict(item)
            item["session_duration_seconds"] = int(item["session_duration_seconds"])
        return SessionState(**item)
