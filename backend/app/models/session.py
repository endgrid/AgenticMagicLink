from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class SessionState:
    session_id: str
    required_functions: List[str] = field(default_factory=list)
    target_account_id: str | None = None
    generated_policy_json: str | None = None
    magic_link_script: str | None = None
