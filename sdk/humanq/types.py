from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class RequestType(StrEnum):
    APPROVAL = "approval"
    CHOICE = "choice"
    CREDENTIAL = "credential"
    CLARIFICATION = "clarification"


@dataclass(frozen=True)
class Resolution:
    request_id: str
    resolution: str
    resolved_at: datetime | None


@dataclass(frozen=True)
class Request:
    id: str
    agent_id: str
    agent_name: str
    request_type: RequestType
    title: str
    detail: str
    options: list[str] | None
    blocked_tasks: int
    status: str
    resolution: str | None
    score: int
    created_at: datetime
    resolved_at: datetime | None
