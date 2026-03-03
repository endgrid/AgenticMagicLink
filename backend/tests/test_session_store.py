# ruff: noqa: E402

import json
import sys
import types
from pathlib import Path

# Lightweight SDK stubs so tests can run in environments without boto3/botocore installed.
boto3_stub = types.ModuleType("boto3")
boto3_stub.client = lambda *_args, **_kwargs: None
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.session_store import InMemorySessionStore, PolicyFailureDLQ
from src.bedrock_client import BedrockInvocationError


class FakeBedrockClient:
    def __init__(self, *, response=None, exc=None, max_attempts=2, last_attempts_used=1):
        self.response = response
        self.exc = exc
        self.max_attempts = max_attempts
        self.last_attempts_used = last_attempts_used

    def generate_policy_from_functions(self, _functions_text):
        if self.exc:
            raise self.exc
        return self.response


class FakeDLQ:
    def __init__(self):
        self.payloads = []

    def enqueue(self, payload):
        self.payloads.append(payload)


def test_update_from_message_generates_policy_json():
    bedrock = FakeBedrockClient(response={"Version": "2012-10-17", "Statement": []})
    store = InMemorySessionStore(bedrock_client=bedrock, failure_dlq=FakeDLQ())
    session = store.create_session()

    updated = store.update_from_message(session.session_id, "please generate policy")

    assert json.loads(updated.generated_policy_json) == {"Version": "2012-10-17", "Statement": []}


def test_update_from_message_enqueues_failure_for_invocation_error():
    dlq = FakeDLQ()
    bedrock = FakeBedrockClient(exc=BedrockInvocationError("timed out"), max_attempts=3)
    store = InMemorySessionStore(bedrock_client=bedrock, failure_dlq=dlq)
    session = store.create_session()

    updated = store.update_from_message(session.session_id, "generate policy")

    assert updated.generated_policy_json is None
    assert len(dlq.payloads) == 1
    assert dlq.payloads[0]["failure_type"] == "retry_exhausted"


def test_policy_dlq_noop_without_url():
    dlq = PolicyFailureDLQ(queue_url=None, sqs_client=None)
    dlq.enqueue({"message": "ignored"})


def test_account_id_prompted_for_role_arn():
    store = InMemorySessionStore()
    session = store.create_session()

    updated = store.update_from_message(session.session_id, "target account is 123456789012")

    assert updated.target_account_id == "123456789012"
    assert updated.workflow_message == "Create the contractor role in AWS, then send me the role ARN."


def test_invalid_role_arn_sets_validation_error():
    store = InMemorySessionStore()
    session = store.create_session()
    store.update_from_message(session.session_id, "target account is 123456789012")

    updated = store.update_from_message(session.session_id, "role arn:aws:iam::123456789012:user/not-a-role")

    assert updated.target_role_arn is None
    assert "couldn't validate" in (updated.workflow_message or "").lower()


def test_valid_role_arn_generates_script():
    store = InMemorySessionStore()
    session = store.create_session()
    store.update_from_message(session.session_id, "target account 123456789012")

    updated = store.update_from_message(
        session.session_id,
        "Here is role arn:aws:iam::123456789012:role/ContractorRole",
    )

    assert updated.target_role_arn == "arn:aws:iam::123456789012:role/ContractorRole"
    assert updated.magic_link_script is not None
    assert "DEFAULT_ROLE_ARN = \"arn:aws:iam::123456789012:role/ContractorRole\"" in updated.magic_link_script
