import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError


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

    @classmethod
    def from_env(
        cls,
        *,
        boto3_session: Optional[Any] = None,
        runtime_client: Optional[Any] = None,
        max_attempts: int = 2,
    ) -> "BedrockClient":
        model_id = os.getenv("BEDROCK_MODEL_ID")
        if not model_id:
            raise BedrockConfigurationError("BEDROCK_MODEL_ID environment variable is required.")

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

        try:
            client = runtime_client or session.client("bedrock-runtime", region_name=region)
        except Exception as exc:  # pragma: no cover - defensive client creation guard
            raise BedrockConfigurationError(f"Failed to initialize bedrock-runtime client: {exc}") from exc

        return cls(model_id=model_id, runtime_client=client, max_attempts=max_attempts)

    def generate_policy_from_functions(self, functions_text: str) -> Dict[str, Any]:
        if not functions_text or not functions_text.strip():
            raise ValueError("functions_text must be non-empty.")

        last_error: Optional[Exception] = None

        for attempt in range(1, self.max_attempts + 1):
            prompt = self._build_prompt(functions_text, retry=attempt > 1)

            try:
                model_output = self._invoke_bedrock(prompt)
                policy = self._extract_policy(model_output)
                self._validate_policy(policy)
                return policy
            except (BedrockInvocationError, BedrockOutputError) as exc:
                last_error = exc
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
            raise BedrockInvocationError(f"Failed to parse Bedrock response payload: {exc}") from exc

        text = self._extract_text_from_payload(payload)
        if not text:
            raise BedrockInvocationError("Bedrock returned an empty text response.")

        return text

    def _extract_text_from_payload(self, payload: Dict[str, Any]) -> str:
        content = payload.get("content", [])
        if isinstance(content, list):
            chunks = [item.get("text", "") for item in content if isinstance(item, dict)]
            return "".join(chunks).strip()

        return ""

    def _extract_policy(self, model_output: str) -> Dict[str, Any]:
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

    def _validate_policy(self, policy: Dict[str, Any]) -> None:
        if not isinstance(policy, dict):
            raise BedrockOutputError("Model output must be a JSON object.")

        if "Version" not in policy or "Statement" not in policy:
            raise BedrockOutputError("IAM policy must include Version and Statement.")

        if not isinstance(policy["Statement"], list):
            raise BedrockOutputError("IAM policy Statement must be a list.")
