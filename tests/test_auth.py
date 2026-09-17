from collections.abc import Iterator
from pathlib import Path
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from board.auth import generate_api_key, hash_api_key, require_admin, require_agent
from board.config import Settings, get_settings
from board.db import get_db, init_db, make_engine
from board.models import Agent

ADMIN_KEY = "admin-secret"
AGENT_KEY = "hq_agent_key"


@pytest.fixture
def engine(tmp_path: Path) -> Engine:
    engine = make_engine(str(tmp_path / "board.db"))
    init_db(engine)
    with Session(engine) as session:
        session.add(
            Agent(
                name="worker-1",
                harness="claude-code",
                api_key_hash=hash_api_key(AGENT_KEY),
            )
        )
        session.commit()
    return engine


@pytest.fixture
def client(engine: Engine) -> TestClient:
    app = FastAPI()

    @app.get("/admin", dependencies=[Depends(require_admin)])
    def admin_route() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/me")
    def me_route(agent: Annotated[Agent, Depends(require_agent)]) -> dict[str, str]:
        return {"id": agent.id, "name": agent.name}

    def override_db() -> Iterator[Session]:
        session = Session(engine)
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = lambda: Settings(
        board_admin_key=ADMIN_KEY,
        _env_file=None,
    )
    return TestClient(app)


def test_generate_api_key_is_prefixed_and_unique() -> None:
    first = generate_api_key()
    second = generate_api_key()
    assert first.startswith("hq_")
    assert first != second


def test_hash_api_key_is_deterministic() -> None:
    assert hash_api_key("hq_abc") == hash_api_key("hq_abc")
    assert hash_api_key("hq_abc") != hash_api_key("hq_abd")
    assert len(hash_api_key("hq_abc")) == 64


def test_require_admin_accepts_the_configured_key(client: TestClient) -> None:
    response = client.get("/admin", headers={"Authorization": f"Bearer {ADMIN_KEY}"})
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_require_admin_rejects_a_wrong_key(client: TestClient) -> None:
    response = client.get("/admin", headers={"Authorization": "Bearer wrong-key"})
    assert response.status_code == 401


def test_require_admin_rejects_a_missing_header(client: TestClient) -> None:
    response = client.get("/admin")
    assert response.status_code == 401


def test_require_agent_returns_the_agent_for_a_valid_key(client: TestClient) -> None:
    response = client.get("/me", headers={"Authorization": f"Bearer {AGENT_KEY}"})
    assert response.status_code == 200
    assert response.json()["name"] == "worker-1"


def test_require_agent_rejects_an_unknown_key(client: TestClient) -> None:
    response = client.get("/me", headers={"Authorization": "Bearer hq_nope"})
    assert response.status_code == 401


def test_require_agent_rejects_a_missing_header(client: TestClient) -> None:
    response = client.get("/me")
    assert response.status_code == 401


def test_require_agent_updates_last_seen(client: TestClient, engine: Engine) -> None:
    with Session(engine) as session:
        before = session.scalar(select(Agent).where(Agent.name == "worker-1"))
        assert before is not None
        assert before.last_seen is None

    client.get("/me", headers={"Authorization": f"Bearer {AGENT_KEY}"})

    with Session(engine) as session:
        after = session.scalar(select(Agent).where(Agent.name == "worker-1"))
        assert after is not None
        assert after.last_seen is not None
        assert after.last_seen.tzinfo is not None
