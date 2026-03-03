# ruff: noqa: E402

import json
import sys
import types
from types import SimpleNamespace

import pytest

# Lightweight SDK stubs so tests can run in environments without boto3/botocore installed.
boto3_stub = types.ModuleType("boto3")
boto3_stub.session = types.SimpleNamespace(Session=lambda: None)
sys.modules.setdefault("boto3", boto3_stub)

botocore_stub = types.ModuleType("botocore")
botocore_exceptions_stub = types.ModuleType("botocore.exceptions")


class _BotoCoreError(Exception):
    pass


class _ClientError(Exception):
    pass


botocore_exceptions_stub.BotoCoreError = _BotoCoreError
botocore_exceptions_stub.ClientError = _ClientError
botocore_stub.exceptions = botocore_exceptions_stub
sys.modules.setdefault("botocore", botocore_stub)
sys.modules.setdefault("botocore.exceptions", botocore_exceptions_stub)

from backend.src.bedrock_client import BedrockClient, BedrockConfigurationError, BedrockOutputError


class FakeBody:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload)


class FakeRuntimeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def invoke_model(self, **kwargs):
        idx = self.calls
        self.calls += 1
        payload = self.responses[idx]
        return {"body": FakeBody(payload)}


class FakeSSMClient:
    def __init__(self, value):
        self.value = value

    def get_parameter(self, **_kwargs):
        return {"Parameter": {"Value": self.value}}


class FakeSecretsClient:
    def __init__(self, value):
        self.value = value

    def get_secret_value(self, **_kwargs):
        return {"SecretString": self.value}


class FakeSession:
    def __init__(
        self,
        *,
        region="us-east-1",
        has_credentials=True,
        runtime_client=None,
        ssm_client=None,
        secrets_client=None,
    ):
        self.region_name = region
        self._has_credentials = has_credentials
        self._runtime_client = runtime_client
        self._ssm_client = ssm_client
        self._secrets_client = secrets_client

    def get_credentials(self):
        return SimpleNamespace(token="x") if self._has_credentials else None

    def client(self, name, *_args, **_kwargs):
        if name == "bedrock-runtime":
            return self._runtime_client
        if name == "ssm":
            return self._ssm_client
        if name == "secretsmanager":
            return self._secrets_client
        return None


@pytest.fixture
def set_model_id(monkeypatch):
    monkeypatch.setenv("BEDROCK_MODEL_ID", "anthropic.claude-opus-4-6")


def test_generate_policy_valid_response(set_model_id):
    output_json = json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [{"Effect": "Allow", "Action": ["s3:GetObject"], "Resource": "*"}],
        }
    )
    payload = {"content": [{"type": "text", "text": output_json}]}
    runtime_client = FakeRuntimeClient([payload])
    session = FakeSession(runtime_client=runtime_client)
    client = BedrockClient.from_env(boto3_session=session)

    policy = client.generate_policy_from_functions("def handler(event, context): pass")

    assert policy["Version"] == "2012-10-17"
    assert len(policy["Statement"]) == 1
    assert runtime_client.calls == 1


def test_generate_policy_retries_on_malformed_json(set_model_id):
    malformed = {"content": [{"type": "text", "text": "not json"}]}
    valid_output = json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {"Effect": "Allow", "Action": ["logs:CreateLogGroup"], "Resource": "*"}
            ],
        }
    )
    valid = {"content": [{"type": "text", "text": valid_output}]}

    runtime_client = FakeRuntimeClient([malformed, valid])
    session = FakeSession(runtime_client=runtime_client)
    client = BedrockClient.from_env(boto3_session=session, max_attempts=2)

    policy = client.generate_policy_from_functions("def handler(event, context): pass")

    assert policy["Statement"][0]["Action"] == ["logs:CreateLogGroup"]
    assert runtime_client.calls == 2
    assert client.last_attempts_used == 2


def test_generate_policy_fails_after_retry_exhausted(set_model_id):
    malformed = {"content": [{"type": "text", "text": "still bad"}]}
    runtime_client = FakeRuntimeClient([malformed, malformed])
    session = FakeSession(runtime_client=runtime_client)
    client = BedrockClient.from_env(boto3_session=session, max_attempts=2)

    with pytest.raises(BedrockOutputError):
        client.generate_policy_from_functions("def handler(event, context): pass")

    assert runtime_client.calls == 2


def test_model_id_from_ssm(monkeypatch):
    monkeypatch.delenv("BEDROCK_MODEL_ID", raising=False)
    monkeypatch.setenv("BEDROCK_MODEL_ID_PARAMETER", "/agentic/bedrock/model-id")

    session = FakeSession(
        runtime_client=FakeRuntimeClient([]),
        ssm_client=FakeSSMClient("anthropic.claude-sonnet-4"),
    )
    client = BedrockClient.from_env(boto3_session=session)

    assert client.model_id == "anthropic.claude-sonnet-4"


def test_model_id_from_secret_json(monkeypatch):
    monkeypatch.delenv("BEDROCK_MODEL_ID", raising=False)
    monkeypatch.delenv("BEDROCK_MODEL_ID_PARAMETER", raising=False)
    monkeypatch.setenv("BEDROCK_MODEL_ID_SECRET_ID", "agentic/model")
    monkeypatch.setenv("BEDROCK_MODEL_ID_SECRET_KEY", "approved_model")

    secret_value = json.dumps({"approved_model": "anthropic.claude-3-5-sonnet"})
    session = FakeSession(
        runtime_client=FakeRuntimeClient([]),
        secrets_client=FakeSecretsClient(secret_value),
    )

    client = BedrockClient.from_env(boto3_session=session)

    assert client.model_id == "anthropic.claude-3-5-sonnet"


def test_missing_region_raises_configuration_error(set_model_id):
    session = FakeSession(region=None, runtime_client=FakeRuntimeClient([]))

    with pytest.raises(BedrockConfigurationError):
        BedrockClient.from_env(boto3_session=session)


def test_missing_credentials_raises_configuration_error(set_model_id):
    session = FakeSession(has_credentials=False, runtime_client=FakeRuntimeClient([]))

    with pytest.raises(BedrockConfigurationError):
        BedrockClient.from_env(boto3_session=session)
