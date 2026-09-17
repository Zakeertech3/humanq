import asyncio
from collections.abc import Iterator

import httpx
import pytest
from fastapi.testclient import TestClient
from humanq import Client, HumanqError, RequestType


class ASGISyncTransport(httpx.BaseTransport):
    def __init__(self, app: object) -> None:
        self.asgi = httpx.ASGITransport(app=app)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        async def run() -> httpx.Response:
            sent = httpx.Request(
                method=request.method,
                url=request.url,
                headers=request.headers,
                content=request.content,
            )
            response = await self.asgi.handle_async_request(sent)
            await response.aread()
            return httpx.Response(
                status_code=response.status_code,
                headers=response.headers,
                content=response.content,
            )

        return asyncio.run(run())


@pytest.fixture
def agent_key(app_client: TestClient, admin_headers: dict[str, str]) -> str:
    response = app_client.post(
        "/agents",
        json={"name": "sdk-worker", "harness": "sdk"},
        headers=admin_headers,
    )
    assert response.status_code == 201
    return str(response.json()["api_key"])


@pytest.fixture
def sdk(app_client: TestClient, agent_key: str) -> Iterator[Client]:
    client = Client(
        base_url="http://testserver",
        api_key=agent_key,
        transport=ASGISyncTransport(app_client.app),
    )
    with client:
        yield client


def resolve_as_admin(
    app_client: TestClient,
    admin_headers: dict[str, str],
    request_id: str,
    text: str,
) -> None:
    response = app_client.post(
        f"/requests/{request_id}/resolve",
        json={"resolution": text},
        headers=admin_headers,
    )
    assert response.status_code == 200


def test_file_request_returns_an_open_request(sdk: Client) -> None:
    request = sdk.file_request(
        RequestType.APPROVAL,
        "Deploy to prod",
        "Release 1.4 is ready",
        blocked_tasks=2,
    )
    assert request.status == "open"
    assert request.request_type is RequestType.APPROVAL
    assert request.agent_name == "sdk-worker"
    assert request.blocked_tasks == 2
    assert request.score == 20
    assert request.resolved_at is None
    assert request.created_at.tzinfo is not None


def test_file_request_carries_options(sdk: Client) -> None:
    request = sdk.file_request(
        RequestType.CHOICE,
        "Which database",
        "Pick one",
        options=["sqlite", "postgres"],
    )
    assert request.options == ["sqlite", "postgres"]


def test_get_request_round_trips(sdk: Client) -> None:
    created = sdk.file_request(RequestType.APPROVAL, "Deploy", "ready")
    fetched = sdk.get_request(created.id)
    assert fetched.id == created.id
    assert fetched.title == "Deploy"


def test_wait_for_resolution_returns_once_the_admin_resolves(
    sdk: Client,
    app_client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    request = sdk.file_request(RequestType.APPROVAL, "Deploy", "ready")
    calls: list[float] = []

    def resolve_then_continue(seconds: float) -> None:
        calls.append(seconds)
        resolve_as_admin(app_client, admin_headers, request.id, "Approved, ship it")

    resolution = sdk.wait_for_resolution(request.id, poll_interval=0.0, sleep=resolve_then_continue)

    assert resolution.request_id == request.id
    assert resolution.resolution == "Approved, ship it"
    assert resolution.resolved_at is not None
    assert calls == [0.0]


def test_wait_for_resolution_times_out_when_never_resolved(sdk: Client) -> None:
    request = sdk.file_request(RequestType.APPROVAL, "Deploy", "ready")

    def no_sleep(seconds: float) -> None:
        return

    with pytest.raises(TimeoutError):
        sdk.wait_for_resolution(request.id, poll_interval=0.0, timeout=0.05, sleep=no_sleep)


def test_ask_files_and_waits(
    sdk: Client,
    app_client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    pending: list[str] = []

    def resolve_latest(seconds: float) -> None:
        listed = app_client.get("/requests?status=open", headers=admin_headers).json()
        for item in listed:
            pending.append(item["id"])
            resolve_as_admin(app_client, admin_headers, item["id"], "Use sqlite")

    resolution = sdk.ask(
        RequestType.CHOICE,
        "Which database",
        "Pick one",
        options=["sqlite", "postgres"],
        poll_interval=0.0,
        sleep=resolve_latest,
    )

    assert resolution.resolution == "Use sqlite"
    assert len(pending) == 1


def test_bad_api_key_raises_humanq_error_with_401(app_client: TestClient) -> None:
    client = Client(
        base_url="http://testserver",
        api_key="hq_not_a_real_key",
        transport=ASGISyncTransport(app_client.app),
    )
    with client, pytest.raises(HumanqError) as caught:
        client.file_request(RequestType.APPROVAL, "Deploy", "ready")

    assert caught.value.status == 401
    assert "401" in str(caught.value)


def test_missing_url_names_the_environment_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HUMANQ_URL", raising=False)
    monkeypatch.delenv("HUMANQ_API_KEY", raising=False)

    with pytest.raises(HumanqError) as caught:
        Client()

    assert "HUMANQ_URL" in str(caught.value)


def test_missing_api_key_names_the_environment_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUMANQ_URL", "http://testserver")
    monkeypatch.delenv("HUMANQ_API_KEY", raising=False)

    with pytest.raises(HumanqError) as caught:
        Client()

    assert "HUMANQ_API_KEY" in str(caught.value)


def test_environment_variables_supply_the_defaults(
    app_client: TestClient,
    agent_key: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HUMANQ_URL", "http://testserver")
    monkeypatch.setenv("HUMANQ_API_KEY", agent_key)

    client = Client(transport=ASGISyncTransport(app_client.app))
    with client:
        request = client.file_request(RequestType.CLARIFICATION, "Which env", "staging or prod")

    assert request.status == "open"
    assert client.base_url == "http://testserver"
