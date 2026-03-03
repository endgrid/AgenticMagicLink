from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class WorkflowState(str, Enum):
    INTRO = "INTRO"
    ASK_FUNCTIONS = "ASK_FUNCTIONS"
    ASK_ACCOUNT = "ASK_ACCOUNT"
    RETURN_SCRIPT = "RETURN_SCRIPT"
    DONE = "DONE"


@dataclass
class SessionData:
    state: WorkflowState = WorkflowState.INTRO
    functions: List[str] = field(default_factory=list)
    policy: Optional[Dict] = None
    account_id: Optional[str] = None


@dataclass
class ChatRequest:
    message: str = ""
    headers: Optional[Dict[str, str]] = None
    cookies: Optional[Dict[str, str]] = None


@dataclass
class ChatResponse:
    body: Dict
    set_cookies: Dict[str, str]


class ContractorAccessBackend:
    def __init__(self) -> None:
        self._sessions: Dict[str, SessionData] = {}

    def _get_or_create_session(self, req: ChatRequest) -> tuple[str, SessionData]:
        headers = {k.lower(): v for k, v in (req.headers or {}).items()}
        cookies = req.cookies or {}

        session_id = headers.get("x-session-id") or cookies.get("session_id")
        if session_id and session_id in self._sessions:
            return session_id, self._sessions[session_id]

        session_id = session_id or str(uuid.uuid4())
        session = SessionData()
        self._sessions[session_id] = session
        return session_id, session

    @staticmethod
    def _parse_functions(message: str) -> List[str]:
        return [part.strip() for part in re.split(r"[\n,]+", message) if part.strip()]

    @staticmethod
    def _build_policy(functions: List[str]) -> Dict:
        statements = []
        for idx, function in enumerate(functions, start=1):
            sid_base = re.sub(r"[^A-Za-z0-9]", "", function.title())[:50] or f"Function{idx}"
            statements.append(
                {
                    "Sid": f"{sid_base}{idx}",
                    "Effect": "Allow",
                    "Action": "*",
                    "Resource": "*",
                }
            )
        return {"Version": "2012-10-17", "Statement": statements}

    @staticmethod
    def _build_script(account_id: str, policy: Dict) -> str:
        serialized_policy = json.dumps(policy, separators=(",", ":"))
        return (
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n\n"
            f"ACCOUNT_ID={account_id}\n"
            "ROLE_NAME=ContractorSessionRole\n"
            f"SESSION_POLICY='{serialized_policy}'\n\n"
            "aws sts assume-role \\\n"
            "  --role-arn \"arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}\" \\\n"
            "  --role-session-name contractor-access-session \\\n"
            "  --policy \"${SESSION_POLICY}\"\n"
        )

    def chat(self, req: ChatRequest) -> ChatResponse:
        sid, session = self._get_or_create_session(req)
        message = req.message.strip()

        if session.state == WorkflowState.INTRO:
            session.state = WorkflowState.ASK_FUNCTIONS
            body = {"session_id": sid, "state": session.state.value, "response": "Contractor Access Agent"}
            return ChatResponse(body=body, set_cookies={"session_id": sid})

        if session.state == WorkflowState.ASK_FUNCTIONS:
            functions = self._parse_functions(message)
            if not functions:
                return ChatResponse(
                    body={
                        "session_id": sid,
                        "state": session.state.value,
                        "response": "Please provide at least one non-empty contractor function description.",
                    },
                    set_cookies={"session_id": sid},
                )

            session.functions = functions
            session.policy = self._build_policy(functions)
            session.state = WorkflowState.ASK_ACCOUNT
            return ChatResponse(
                body={
                    "session_id": sid,
                    "state": session.state.value,
                    "policy": session.policy,
                    "response": "Please provide the 12-digit AWS account ID.",
                },
                set_cookies={"session_id": sid},
            )

        if session.state == WorkflowState.ASK_ACCOUNT:
            if not re.fullmatch(r"\d{12}", message):
                return ChatResponse(
                    body={
                        "session_id": sid,
                        "state": session.state.value,
                        "response": "Invalid AWS account ID. Please provide a 12-digit account number.",
                    },
                    set_cookies={"session_id": sid},
                )

            session.account_id = message
            script = self._build_script(session.account_id, session.policy or self._build_policy(session.functions))
            session.state = WorkflowState.RETURN_SCRIPT
            return ChatResponse(
                body={"session_id": sid, "state": session.state.value, "script": script, "response": "Generated script."},
                set_cookies={"session_id": sid},
            )

        if session.state == WorkflowState.RETURN_SCRIPT:
            session.state = WorkflowState.DONE
            return ChatResponse(
                body={"session_id": sid, "state": session.state.value, "response": "Workflow complete."},
                set_cookies={"session_id": sid},
            )

        return ChatResponse(
            body={"session_id": sid, "state": session.state.value, "response": "Workflow already complete."},
            set_cookies={"session_id": sid},
        )


backend = ContractorAccessBackend()
