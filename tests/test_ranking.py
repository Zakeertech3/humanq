from datetime import UTC, datetime, timedelta

import pytest

from board.enums import RequestType
from board.ranking import score

CREATED = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
NAIVE = datetime(2026, 1, 1, 12, 0)


def test_zero_blocked_and_zero_wait_scores_zero() -> None:
    assert score(0, CREATED, RequestType.APPROVAL, CREATED) == 0


@pytest.mark.parametrize(
    ("blocked_tasks", "expected"),
    [(0, 0), (1, 10), (3, 30), (10, 100)],
)
def test_blocked_tasks_scale_by_ten(blocked_tasks: int, expected: int) -> None:
    assert score(blocked_tasks, CREATED, RequestType.APPROVAL, CREATED) == expected


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(0, 0), (59, 0), (60, 1), (119, 1), (120, 2), (3600, 60)],
)
def test_waiting_counts_whole_minutes_only(seconds: int, expected: int) -> None:
    now = CREATED + timedelta(seconds=seconds)
    assert score(0, CREATED, RequestType.APPROVAL, now) == expected


def test_credential_adds_twenty_five_over_clarification() -> None:
    now = CREATED + timedelta(minutes=5)
    clarification = score(2, CREATED, RequestType.CLARIFICATION, now)
    credential = score(2, CREATED, RequestType.CREDENTIAL, now)
    assert clarification == 25
    assert credential - clarification == 25


def test_plain_credential_string_gets_the_bonus() -> None:
    now = CREATED + timedelta(minutes=5)
    assert score(2, CREATED, "credential", now) == 50


def test_now_earlier_than_created_at_clamps_waiting_to_zero() -> None:
    now = CREATED - timedelta(hours=3)
    assert score(1, CREATED, RequestType.APPROVAL, now) == 10


def test_naive_created_at_raises_value_error() -> None:
    with pytest.raises(ValueError):
        score(0, NAIVE, RequestType.APPROVAL, CREATED)


def test_naive_now_raises_value_error() -> None:
    with pytest.raises(ValueError):
        score(0, CREATED, RequestType.APPROVAL, NAIVE)
