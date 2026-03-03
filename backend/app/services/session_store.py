from __future__ import annotations

import uuid
from typing import Dict

from app.models.session import SessionState


class InMemorySessionStore:
    """Simple in-memory session store; can be replaced with Redis/DB later."""

    def __init__(self) -> None:
        self._sessions: Dict[str, SessionState] = {}

    def create_session(self) -> SessionState:
        session = SessionState(session_id=str(uuid.uuid4()))
        self._sessions[session.session_id] = session
        return session

    def get_session(self, session_id: str) -> SessionState | None:
        return self._sessions.get(session_id)

    def update_from_message(self, session_id: str, user_message: str) -> SessionState:
        session = self._sessions[session_id]

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

        return session
