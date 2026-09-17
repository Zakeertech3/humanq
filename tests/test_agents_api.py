from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from board.auth import hash_api_key
from board.config import Settings
from board.main import create_app
from board.models import Agent, Request

ADMIN_KEY = "test-admin-key"
ADMIN_HEADERS = {"Authorization": f"Bearer {ADMIN_KEY}"}


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(
        board_db_path=str(tmp_path / "board.db"),
        board_admin_key=ADMIN_KEY,
        _env_file=None,
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def engine_of(client: TestClient) -> Engine:
    return client.app.state.engine


def create_agent(client: TestClient, name: str = "worker-1") -> dict[str, str]:
    response = client.post(
        "/agents",
        json={"name": name, "harness": "claude-code"},
        headers=ADMIN_HEADERS,
    )
    assert response.status_code == 201
    return response.json()


def test_create_agent_returns_a_prefixed_key_and_stores_only_its_hash(
    client: TestClient,
) -> None:
    body = create_agent(client)
    api_key = body["api_key"]
    assert api_key.startswith("hq_")
    assert body["name"] == "worker-1"

    with Session(engine_of(client)) as session:
        stored = session.scalar(select(Agent).where(Agent.name == "worker-1"))
        assert stored is not None
        assert stored.api_key_hash == hash_api_key(api_key)
        assert stored.api_key_hash != api_key


def test_create_agent_rejects_a_duplicate_name(client: TestClient) -> None:
    create_agent(client)
    response = client.post(
        "/agents",
        json={"name": "worker-1", "harness": "codex"},
        headers=ADMIN_HEADERS,
    )
    assert response.status_code == 409


def test_create_agent_requires_admin(client: TestClient) -> None:
    response = client.post(
        "/agents",
        json={"name": "worker-1", "harness": "codex"},
        headers={"Authorization": "Bearer wrong"},
    )
    assert response.status_code == 401


def test_list_agents_requires_admin_and_returns_the_created_agent(client: TestClient) -> None:
    create_agent(client)

    assert client.get("/agents").status_code == 401
    assert client.get("/agents", headers={"Authorization": "Bearer wrong"}).status_code == 401

    response = client.get("/agents", headers=ADMIN_HEADERS)
    assert response.status_code == 200
    names = [agent["name"] for agent in response.json()]
    assert names == ["worker-1"]


def test_list_agents_is_ordered_by_name(client: TestClient) -> None:
    create_agent(client, name="zulu")
    create_agent(client, name="alpha")
    create_agent(client, name="mike")

    response = client.get("/agents", headers=ADMIN_HEADERS)
    names = [agent["name"] for agent in response.json()]
    assert names == ["alpha", "mike", "zulu"]


def test_agents_me_returns_the_calling_agent(client: TestClient) -> None:
    body = create_agent(client)

    response = client.get("/agents/me", headers={"Authorization": f"Bearer {body['api_key']}"})
    assert response.status_code == 200
    assert response.json()["id"] == body["id"]
    assert "api_key" not in response.json()


def test_agents_me_rejects_a_wrong_key(client: TestClient) -> None:
    create_agent(client)
    response = client.get("/agents/me", headers={"Authorization": "Bearer hq_wrong"})
    assert response.status_code == 401


def test_delete_unknown_agent_returns_404(client: TestClient) -> None:
    response = client.delete("/agents/does-not-exist", headers=ADMIN_HEADERS)
    assert response.status_code == 404


def test_delete_agent_without_requests_returns_204(client: TestClient) -> None:
    body = create_agent(client)

    response = client.delete(f"/agents/{body['id']}", headers=ADMIN_HEADERS)
    assert response.status_code == 204

    listed = client.get("/agents", headers=ADMIN_HEADERS)
    assert listed.json() == []


def test_delete_agent_with_open_requests_returns_409(client: TestClient) -> None:
    body = create_agent(client)

    with Session(engine_of(client)) as session:
        session.add(
            Request(
                agent_id=body["id"],
                request_type="approval",
                title="Deploy to prod",
                detail="ready",
                status="open",
            )
        )
        session.commit()

    response = client.delete(f"/agents/{body['id']}", headers=ADMIN_HEADERS)
    assert response.status_code == 409

    listed = client.get("/agents", headers=ADMIN_HEADERS)
    assert len(listed.json()) == 1
