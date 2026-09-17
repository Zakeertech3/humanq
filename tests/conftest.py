from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from board.config import Settings
from board.main import create_app

ADMIN_KEY = "test-admin-key"


@pytest.fixture
def app_client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(
        board_db_path=str(tmp_path / "board.db"),
        board_admin_key=ADMIN_KEY,
        _env_file=None,
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def admin_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {ADMIN_KEY}"}


def register_agent(
    client: TestClient,
    admin_headers: dict[str, str],
    name: str,
) -> dict[str, str]:
    response = client.post(
        "/agents",
        json={"name": name, "harness": "claude-code"},
        headers=admin_headers,
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['api_key']}"}


@pytest.fixture
def agent_headers(app_client: TestClient, admin_headers: dict[str, str]) -> dict[str, str]:
    return register_agent(app_client, admin_headers, "worker-1")


@pytest.fixture
def other_agent_headers(app_client: TestClient, admin_headers: dict[str, str]) -> dict[str, str]:
    return register_agent(app_client, admin_headers, "worker-2")
