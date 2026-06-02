"""Request/response schemas for the API."""
from typing import List, Literal, Optional

from pydantic import BaseModel


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    # Full conversation so the agent has context; the last message is the new turn.
    messages: List[Message]
    # Optional model number the user pinned in the UI ("your model" chip).
    model_number: Optional[str] = None


class ChatResponse(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: str
    cards: List[dict] = []
    suggestions: List[str] = []
    tools_used: List[str] = []
