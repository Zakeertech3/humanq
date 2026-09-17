from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from board.enums import RequestType
from board.schemas import EventOut, RequestCreate, RequestOut

CREATED = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def test_request_create_accepts_a_valid_payload() -> None:
    created = RequestCreate(
        request_type=RequestType.CHOICE,
        title="Pick a database",
        detail="sqlite or postgres",
        options=["sqlite", "postgres"],
        blocked_tasks=3,
    )
    assert created.request_type is RequestType.CHOICE
    assert created.options == ["sqlite", "postgres"]
    assert created.options_json() == '["sqlite", "postgres"]'


def test_request_create_defaults_options_to_none_and_blocked_tasks_to_zero() -> None:
    created = RequestCreate(
        request_type=RequestType.APPROVAL,
        title="Deploy",
        detail="ready",
    )
    assert created.options is None
    assert created.blocked_tasks == 0
    assert created.options_json() is None


def test_request_create_rejects_an_empty_title() -> None:
    with pytest.raises(ValidationError):
        RequestCreate(request_type=RequestType.APPROVAL, title="", detail="detail")


def test_request_create_rejects_eleven_options() -> None:
    with pytest.raises(ValidationError):
        RequestCreate(
            request_type=RequestType.CHOICE,
            title="Pick one",
            detail="detail",
            options=[str(index) for index in range(11)],
        )


def test_request_create_accepts_ten_options() -> None:
    created = RequestCreate(
        request_type=RequestType.CHOICE,
        title="Pick one",
        detail="detail",
        options=[str(index) for index in range(10)],
    )
    assert created.options is not None
    assert len(created.options) == 10


def test_request_create_rejects_negative_blocked_tasks() -> None:
    with pytest.raises(ValidationError):
        RequestCreate(
            request_type=RequestType.APPROVAL,
            title="Deploy",
            detail="detail",
            blocked_tasks=-1,
        )


def test_request_out_round_trips_options_from_a_json_string() -> None:
    out = RequestOut.model_validate(
        {
            "id": "r1",
            "agent_id": "a1",
            "agent_name": "worker-1",
            "request_type": "choice",
            "title": "Pick a database",
            "detail": "sqlite or postgres",
            "options": '["sqlite", "postgres"]',
            "blocked_tasks": 2,
            "status": "open",
            "resolution": None,
            "score": 25,
            "created_at": CREATED,
            "resolved_at": None,
        }
    )
    assert out.options == ["sqlite", "postgres"]
    assert out.request_type is RequestType.CHOICE


def test_request_out_accepts_a_missing_options_value() -> None:
    out = RequestOut.model_validate(
        {
            "id": "r1",
            "agent_id": "a1",
            "agent_name": "worker-1",
            "request_type": "approval",
            "title": "Deploy",
            "detail": "ready",
            "options": None,
            "blocked_tasks": 0,
            "status": "open",
            "resolution": None,
            "score": 0,
            "created_at": CREATED,
            "resolved_at": None,
        }
    )
    assert out.options is None


def test_event_out_round_trips_payload_from_a_json_string() -> None:
    out = EventOut.model_validate(
        {
            "id": 1,
            "request_id": "r1",
            "kind": "created",
            "payload": '{"blocked_tasks": 3}',
            "created_at": CREATED,
        }
    )
    assert out.payload == {"blocked_tasks": 3}
