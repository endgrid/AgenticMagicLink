from __future__ import annotations

import hashlib
import uuid

import boto3

from app.models.session import SessionState
from src.magic_link_script import MAGIC_LINK_SCRIPT_VERSION, generate_magic_link_script

    def enqueue(self, payload: dict[str, object]) -> None:
        if not self.queue_url:
            return

        sqs_client = self._sqs_client or boto3.client("sqs")
        sqs_client.send_message(QueueUrl=self.queue_url, MessageBody=json.dumps(payload))

from ..models.session import SessionState


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
            session.required_functions = [
                item.strip() for item in user_message.split(",") if item.strip()
            ]

        if "target account" in user_message.lower():
            tokens = user_message.split()
            maybe_account_id = next(
                (token for token in tokens if token.isdigit() and len(token) == 12), None
            )
            if maybe_account_id:
                session.target_account_id = maybe_account_id

        if "policy" in user_message.lower():
            policy = self._generate_policy(session, user_message)
            session.generated_policy_json = json.dumps(policy) if policy else None

        if "script" in user_message.lower() or "magic link" in user_message.lower():
            script_content = generate_magic_link_script()
            session.magic_link_script = script_content
            session.magic_link_script_checksum_sha256 = hashlib.sha256(
                script_content.encode("utf-8")
            ).hexdigest()
            session.magic_link_script_version = MAGIC_LINK_SCRIPT_VERSION

        return session

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
