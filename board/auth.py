import hashlib
import hmac
import secrets
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from board.config import Settings, get_settings
from board.db import get_db
from board.models import Agent, utc_now

bearer_scheme = HTTPBearer(auto_error=False)


def generate_api_key() -> str:
    return f"hq_{secrets.token_urlsafe(32)}"


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


def bearer_token(credentials: HTTPAuthorizationCredentials | None) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized()
    if not credentials.credentials:
        raise unauthorized()
    return credentials.credentials


def require_agent(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[Session, Depends(get_db)],
) -> Agent:
    token = bearer_token(credentials)
    agent = session.scalar(select(Agent).where(Agent.api_key_hash == hash_api_key(token)))
    if agent is None:
        raise unauthorized()
    agent.last_seen = utc_now()
    session.commit()
    return agent


@dataclass(frozen=True)
class Caller:
    agent: Agent | None
    is_admin: bool


def require_agent_or_admin(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Caller:
    token = bearer_token(credentials)
    if hmac.compare_digest(token, settings.board_admin_key):
        return Caller(agent=None, is_admin=True)
    agent = session.scalar(select(Agent).where(Agent.api_key_hash == hash_api_key(token)))
    if agent is None:
        raise unauthorized()
    agent.last_seen = utc_now()
    session.commit()
    return Caller(agent=agent, is_admin=False)


def require_admin(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    token = bearer_token(credentials)
    if not hmac.compare_digest(token, settings.board_admin_key):
        raise unauthorized()
