from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from board.auth import generate_api_key, hash_api_key, require_admin, require_agent
from board.db import get_db
from board.models import Agent, Event, Request
from board.schemas import AgentCreate, AgentCreated, AgentOut

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_agent(
    payload: AgentCreate,
    session: Annotated[Session, Depends(get_db)],
) -> AgentCreated:
    api_key = generate_api_key()
    agent = Agent(
        name=payload.name,
        harness=payload.harness,
        api_key_hash=hash_api_key(api_key),
    )
    session.add(agent)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Agent name already exists",
        ) from None
    return AgentCreated(
        id=agent.id,
        name=agent.name,
        harness=agent.harness,
        created_at=agent.created_at,
        last_seen=agent.last_seen,
        api_key=api_key,
    )


@router.get("", dependencies=[Depends(require_admin)])
def list_agents(session: Annotated[Session, Depends(get_db)]) -> list[AgentOut]:
    agents = session.scalars(select(Agent).order_by(Agent.name)).all()
    return [AgentOut.model_validate(agent) for agent in agents]


@router.get("/me")
def read_me(agent: Annotated[Agent, Depends(require_agent)]) -> AgentOut:
    return AgentOut.model_validate(agent)


@router.delete(
    "/{agent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
def delete_agent(
    agent_id: str,
    session: Annotated[Session, Depends(get_db)],
) -> None:
    agent = session.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    open_count = session.scalar(
        select(Request.id).where(Request.agent_id == agent_id, Request.status == "open").limit(1)
    )
    if open_count is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Agent has open requests",
        )

    request_ids = session.scalars(select(Request.id).where(Request.agent_id == agent_id)).all()
    if request_ids:
        session.execute(delete(Event).where(Event.request_id.in_(request_ids)))
        session.execute(delete(Request).where(Request.agent_id == agent_id))
    session.delete(agent)
    session.commit()
