from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MessageRequest(BaseModel):
    content: str = Field(default="", max_length=4000)
    requireApproval: bool = False
    resumeRunId: str | None = None


class ApprovalRequest(BaseModel):
    approve: bool = True
    runId: str = Field(min_length=1)
    callIds: list[str] | None = None


class SessionCreate(BaseModel):
    title: str = Field(default="新的问数会话", max_length=100)


class JsonPayload(BaseModel):
    model_config = {"extra": "allow"}

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)
