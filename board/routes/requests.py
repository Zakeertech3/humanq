from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from board.auth import Caller, require_admin, require_agent, require_agent_or_admin
from board.db import get_db
from board.models import Agent, Event, Request, utc_now
from board.ranking import score
from board.schemas import EventOut, RequestCreate, RequestOut, RequestResolve, dump_json

router = APIRouter(prefix="/requests", tags=["requests"])

StatusFilter = Literal["open", "resolved", "all"]


def to_request_out(request: Request, now: datetime) -> RequestOut:
    effective_now = request.resolved_at if request.resolved_at is not None else now
    return RequestOut(
        id=request.id,
        agent_id=request.agent_id,
        agent_name=request.agent.name,
        request_type=request.request_type,
        title=request.title,
        detail=request.detail,
        options=request.options_json,
        blocked_tasks=request.blocked_tasks,
        status=request.status,
        resolution=request.resolution,
        score=score(request.blocked_tasks, request.created_at, request.request_type, effective_now),
        created_at=request.created_at,
        resolved_at=request.resolved_at,
    )


def ranked(requests: list[Request], now: datetime, limit: int) -> list[RequestOut]:
    items = [to_request_out(request, now) for request in requests]
    items.sort(key=lambda item: (-item.score, item.created_at))
    return items[:limit]


def status_clause(status_filter: StatusFilter) -> list[bool]:
    if status_filter == "all":
        return []
    return [Request.status == status_filter]


def load_request(session: Session, request_id: str) -> Request:
    request = session.scalar(
        select(Request).options(selectinload(Request.agent)).where(Request.id == request_id)
    )
    if request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    return request


def visible_to(request: Request, caller: Caller) -> Request:
    if caller.is_admin:
        return request
    if caller.agent is None or request.agent_id != caller.agent.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    return request


@router.post("", status_code=status.HTTP_201_CREATED)
def create_request(
    payload: RequestCreate,
    agent: Annotated[Agent, Depends(require_agent)],
    session: Annotated[Session, Depends(get_db)],
) -> RequestOut:
    request = Request(
        agent_id=agent.id,
        request_type=payload.request_type.value,
        title=payload.title,
        detail=payload.detail,
        options_json=payload.options_json(),
        blocked_tasks=payload.blocked_tasks,
        status="open",
    )
    session.add(request)
    session.flush()
    session.add(Event(request_id=request.id, kind="created"))
    session.commit()
    return to_request_out(request, utc_now())


@router.get("", dependencies=[Depends(require_admin)])
def list_requests(
    session: Annotated[Session, Depends(get_db)],
    status_filter: Annotated[StatusFilter, Query(alias="status")] = "open",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[RequestOut]:
    requests = session.scalars(
        select(Request).options(selectinload(Request.agent)).where(*status_clause(status_filter))
    ).all()
    return ranked(list(requests), utc_now(), limit)


@router.get("/mine")
def list_my_requests(
    agent: Annotated[Agent, Depends(require_agent)],
    session: Annotated[Session, Depends(get_db)],
    status_filter: Annotated[StatusFilter, Query(alias="status")] = "open",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[RequestOut]:
    requests = session.scalars(
        select(Request)
        .options(selectinload(Request.agent))
        .where(Request.agent_id == agent.id, *status_clause(status_filter))
    ).all()
    return ranked(list(requests), utc_now(), limit)


@router.get("/{request_id}")
def read_request(
    request_id: str,
    caller: Annotated[Caller, Depends(require_agent_or_admin)],
    session: Annotated[Session, Depends(get_db)],
) -> RequestOut:
    request = visible_to(load_request(session, request_id), caller)
    return to_request_out(request, utc_now())


@router.post("/{request_id}/resolve", dependencies=[Depends(require_admin)])
def resolve_request(
    request_id: str,
    payload: RequestResolve,
    session: Annotated[Session, Depends(get_db)],
) -> RequestOut:
    request = load_request(session, request_id)
    if request.status == "resolved":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Request is already resolved",
        )
    request.status = "resolved"
    request.resolution = payload.resolution
    request.resolved_at = utc_now()
    session.add(
        Event(
            request_id=request.id,
            kind="resolved",
            payload_json=dump_json({"resolution": payload.resolution}),
        )
    )
    session.commit()
    return to_request_out(request, utc_now())


@router.get("/{request_id}/events")
def list_request_events(
    request_id: str,
    caller: Annotated[Caller, Depends(require_agent_or_admin)],
    session: Annotated[Session, Depends(get_db)],
) -> list[EventOut]:
    visible_to(load_request(session, request_id), caller)
    events = session.scalars(
        select(Event).where(Event.request_id == request_id).order_by(Event.created_at, Event.id)
    ).all()
    return [
        EventOut(
            id=event.id,
            request_id=event.request_id,
            kind=event.kind,
            payload=event.payload_json,
            created_at=event.created_at,
        )
        for event in events
    ]
