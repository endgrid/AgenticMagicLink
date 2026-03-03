from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SessionState:
    session_id: str
    conversation_stage: str = "awaiting_work_description"
    contractor_work_summary: str | None = None
    required_functions: list[str] = field(default_factory=list)
    required_services: list[str] = field(default_factory=list)
    target_account_id: str | None = None
    role_arn: str | None = None
    session_duration_seconds: int | None = None
    generated_policy_json: str | None = None
    next_assistant_prompt: str | None = None
    magic_link_script: str | None = None
    magic_link_script_checksum_sha256: str | None = None
    magic_link_script_version: str | None = None
    workflow_message: str | None = None

    @property
    def target_role_arn(self) -> str | None:
        """Backward-compatible alias for older code/tests."""
        return self.role_arn

    @target_role_arn.setter
    def target_role_arn(self, value: str | None) -> None:
        self.role_arn = value
