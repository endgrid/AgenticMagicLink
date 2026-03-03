import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)


class BedrockError(Exception):
    """Base exception for Bedrock runtime failures."""


class BedrockConfigurationError(BedrockError):
    """Raised when AWS or Bedrock configuration is missing or invalid."""


class BedrockInvocationError(BedrockError):
    """Raised when Bedrock cannot complete a model invocation."""


class BedrockOutputError(BedrockError):
    """Raised when the model response is not valid IAM policy JSON."""


@dataclass
class BedrockClient:
    model_id: str
    runtime_client: Any
    max_attempts: int = 2
    last_attempts_used: int = field(default=0, init=False)

    @classmethod
    def from_env(
        cls,
        *,
        boto3_session: Any | None = None,
        runtime_client: Any | None = None,
        max_attempts: int = 2,
    ) -> "BedrockClient":
        session = boto3_session or boto3.session.Session()

        region = session.region_name
        if not region:
            raise BedrockConfigurationError(
                "AWS region is not configured. Set AWS_REGION or AWS_DEFAULT_REGION."
            )

        credentials = session.get_credentials()
        if credentials is None:
            raise BedrockConfigurationError(
                "AWS credentials are not configured for Bedrock runtime access."
            )

        model_id = cls._resolve_model_id(session)

        try:
            client = runtime_client or session.client("bedrock-runtime", region_name=region)
        except Exception as exc:  # pragma: no cover - defensive client creation guard
            message = f"Failed to initialize bedrock-runtime client: {exc}"
            raise BedrockConfigurationError(message) from exc

        return cls(model_id=model_id, runtime_client=client, max_attempts=max_attempts)

    @staticmethod
    def _resolve_model_id(session: Any) -> str:
        direct_model_id = os.getenv("BEDROCK_MODEL_ID")
        if direct_model_id:
            return direct_model_id

        model_id_param_name = os.getenv("BEDROCK_MODEL_ID_PARAMETER")
        if model_id_param_name:
            try:
                ssm_client = session.client("ssm")
                response = ssm_client.get_parameter(Name=model_id_param_name, WithDecryption=True)
            except (BotoCoreError, ClientError) as exc:
                message = (
                    "Failed to load model ID from SSM parameter "
                    f"'{model_id_param_name}': {exc}"
                )
                raise BedrockConfigurationError(message) from exc

            model_id = response.get("Parameter", {}).get("Value", "").strip()
            if model_id:
                return model_id

            raise BedrockConfigurationError(
                f"SSM parameter '{model_id_param_name}' did not contain a model ID value."
            )

        model_id_secret_id = os.getenv("BEDROCK_MODEL_ID_SECRET_ID")
        if model_id_secret_id:
            secret_key = os.getenv("BEDROCK_MODEL_ID_SECRET_KEY", "model_id")

            try:
                secrets_client = session.client("secretsmanager")
                response = secrets_client.get_secret_value(SecretId=model_id_secret_id)
            except (BotoCoreError, ClientError) as exc:
                message = (
                    "Failed to load model ID from Secrets Manager secret "
                    f"'{model_id_secret_id}': {exc}"
                )
                raise BedrockConfigurationError(message) from exc

            secret_value = response.get("SecretString", "")
            if not secret_value:
                raise BedrockConfigurationError(
                    f"Secret '{model_id_secret_id}' did not contain a SecretString payload."
                )

            try:
                payload = json.loads(secret_value)
            except json.JSONDecodeError as exc:
                if secret_value.strip():
                    return secret_value.strip()
                message = f"Secret '{model_id_secret_id}' did not contain a usable model ID."
                raise BedrockConfigurationError(message) from exc

            model_id = str(payload.get(secret_key, "")).strip()
            if not model_id:
                raise BedrockConfigurationError(
                    f"Secret '{model_id_secret_id}' is missing key '{secret_key}' for model ID."
                )

            return model_id

        raise BedrockConfigurationError(
            "Provide BEDROCK_MODEL_ID, BEDROCK_MODEL_ID_PARAMETER, or BEDROCK_MODEL_ID_SECRET_ID."
        )

    def generate_policy_from_functions(self, functions_text: str) -> dict[str, Any]:
        if not functions_text or not functions_text.strip():
            raise ValueError("functions_text must be non-empty.")

        last_error: Exception | None = None

        for attempt in range(1, self.max_attempts + 1):
            self.last_attempts_used = attempt
            prompt = self._build_prompt(functions_text, retry=attempt > 1)

            try:
                model_output = self._invoke_bedrock(prompt)
                policy = self._extract_policy(model_output)
                self._validate_policy(policy)
                return policy
            except (BedrockInvocationError, BedrockOutputError) as exc:
                last_error = exc
                logger.warning(
                    "bedrock_policy_generation_attempt_failed",
                    extra={
                        "attempt": attempt,
                        "max_attempts": self.max_attempts,
                        "error": str(exc),
                    },
                )
                if attempt >= self.max_attempts:
                    raise

        raise BedrockOutputError(
            f"Unable to produce a valid IAM policy after {self.max_attempts} attempts."
        ) from last_error

    def _build_prompt(self, functions_text: str, *, retry: bool) -> str:
        retry_instructions = ""
        if retry:
            retry_instructions = (
                "Previous response was invalid. Return ONLY a valid JSON IAM policy object "
                "with keys Version and Statement, and no markdown or explanation.\n"
            )

        return (
            "You are an IAM policy generator.\n"
            "Given AWS Lambda function signatures/descriptions, output the least-privilege IAM "
            "policy needed by those functions.\n"
            f"{retry_instructions}"
            "Return JSON only.\n"
            "Required format:\n"
            "{\"Version\":\"2012-10-17\",\"Statement\":[...]}\n\n"
            "Functions input:\n"
            f"{functions_text}"
        )

    def _invoke_bedrock(self, prompt: str) -> str:
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1024,
            "temperature": 0,
            "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
        }

        try:
            response = self.runtime_client.invoke_model(
                modelId=self.model_id,
                body=json.dumps(body),
                contentType="application/json",
                accept="application/json",
            )
        except (BotoCoreError, ClientError, TimeoutError) as exc:
            raise BedrockInvocationError(f"Bedrock invocation failed: {exc}") from exc

        try:
            payload = json.loads(response["body"].read())
        except Exception as exc:
            message = f"Failed to parse Bedrock response payload: {exc}"
            raise BedrockInvocationError(message) from exc

        text = self._extract_text_from_payload(payload)
        if not text:
            raise BedrockInvocationError("Bedrock returned an empty text response.")

        return text

    def _extract_text_from_payload(self, payload: dict[str, Any]) -> str:
        content = payload.get("content", [])
        if isinstance(content, list):
            chunks = [item.get("text", "") for item in content if isinstance(item, dict)]
            return "".join(chunks).strip()

        return ""

    def _extract_policy(self, model_output: str) -> dict[str, Any]:
        candidate = model_output.strip()

        if "```" in candidate:
            parts = [part.strip() for part in candidate.split("```") if part.strip()]
            json_blocks = [part for part in parts if part.startswith("{")]
            if json_blocks:
                candidate = json_blocks[0]

        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise BedrockOutputError(f"Model output was not valid JSON: {exc}") from exc

    def _validate_policy(self, policy: dict[str, Any]) -> None:
        if not isinstance(policy, dict):
            raise BedrockOutputError("Model output must be a JSON object.")

        if "Version" not in policy or "Statement" not in policy:
            raise BedrockOutputError("IAM policy must include Version and Statement.")

        if not isinstance(policy["Statement"], list):
            raise BedrockOutputError("IAM policy Statement must be a list.")
