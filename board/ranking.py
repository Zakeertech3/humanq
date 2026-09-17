from datetime import datetime

from board.enums import RequestType


def score(
    blocked_tasks: int,
    created_at: datetime,
    request_type: RequestType,
    now: datetime,
) -> int:
    if created_at.tzinfo is None or created_at.tzinfo.utcoffset(created_at) is None:
        raise ValueError("created_at must be timezone-aware")
    if now.tzinfo is None or now.tzinfo.utcoffset(now) is None:
        raise ValueError("now must be timezone-aware")
    minutes_waiting = max(0, int((now - created_at).total_seconds() // 60))
    total = blocked_tasks * 10 + minutes_waiting
    if request_type == RequestType.CREDENTIAL:
        total += 25
    return total
