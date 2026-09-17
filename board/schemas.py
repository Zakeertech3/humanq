import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from board.enums import RequestType


def dump_json(value: list[str] | dict[str, Any] | None) -> str | None:
    if value is None:
        return None
    return json.dumps(value)


def load_json(raw: str | None) -> list[str] | dict[str, Any] | None:
    if raw is None:
        return None
    return json.loads(raw)


class RequestCreate(BaseModel):
    request_type: RequestType
    title: str = Field(min_length=1, max_length=200)
    detail: str = Field(max_length=5000)
    options: list[str] | None = Field(default=None, max_length=10)
    blocked_tasks: int = Field(default=0, ge=0)

    def options_json(self) -> str | None:
        return dump_json(self.options)


class RequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    agent_id: str
    agent_name: str
    request_type: RequestType
    title: str
    detail: str
    options: list[str] | None = None
    blocked_tasks: int
    status: str
    resolution: str | None = None
    score: int
    created_at: datetime
    resolved_at: datetime | None = None

    @field_validator("options", mode="before")
    @classmethod
    def parse_options(cls, value: Any) -> Any:
        if isinstance(value, str):
            return load_json(value)
        return value


class RequestResolve(BaseModel):
    resolution: str = Field(min_length=1, max_length=5000)


class AgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    harness: str = Field(min_length=1, max_length=100)


class AgentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    harness: str
    created_at: datetime
    last_seen: datetime | None = None


class AgentCreated(AgentOut):
    api_key: str


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    request_id: str
    kind: str
    payload: dict[str, Any] | None = None
    created_at: datetime

    @field_validator("payload", mode="before")
    @classmethod
    def parse_payload(cls, value: Any) -> Any:
        if isinstance(value, str):
            return load_json(value)
        return value
