from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class SessionResponse(BaseModel):
    session_id: str


class MessageRequest(BaseModel):
    session_id: str
    message: str = Field(min_length=1)
    history: list[ChatMessage] = Field(default_factory=list)


class MessageResponse(BaseModel):
    session_id: str
    messages: list[ChatMessage]
