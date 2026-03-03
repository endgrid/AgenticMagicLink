from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class SessionState:
    session_id: str
    conversation_stage: str = "awaiting_work_description"
    contractor_work_summary: str | None = None
    required_functions: List[str] = field(default_factory=list)
    required_services: List[str] = field(default_factory=list)
    target_account_id: str | None = None
    target_role_arn: str | None = None
    generated_policy_json: str | None = None
    next_assistant_prompt: str | None = None
    magic_link_script: str | None = None
    magic_link_script_checksum_sha256: str | None = None
    magic_link_script_version: str | None = None
    workflow_message: str | None = None
