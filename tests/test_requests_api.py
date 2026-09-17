from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

APPROVAL = {
    "request_type": "approval",
    "title": "Deploy to prod",
    "detail": "Release 1.4 is ready",
    "blocked_tasks": 0,
}


def post_request(
    client: TestClient,
    headers: dict[str, str],
    **overrides: object,
) -> dict[str, object]:
    payload = APPROVAL | overrides
    response = client.post("/requests", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def test_agent_creates_a_request(app_client: TestClient, agent_headers: dict[str, str]) -> None:
    body = post_request(app_client, agent_headers)
    assert body["status"] == "open"
    assert body["score"] == 0
    assert body["agent_name"] == "worker-1"
    assert body["resolution"] is None
    assert body["resolved_at"] is None


def test_unauthenticated_create_is_rejected(app_client: TestClient) -> None:
    response = app_client.post("/requests", json=APPROVAL)
    assert response.status_code == 401


def test_admin_list_returns_the_open_request(
    app_client: TestClient,
    agent_headers: dict[str, str],
    admin_headers: dict[str, str],
) -> None:
    created = post_request(app_client, agent_headers)

    response = app_client.get("/requests", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body] == [created["id"]]
    assert body[0]["status"] == "open"


def test_more_blocked_tasks_ranks_higher(
    app_client: TestClient,
    agent_headers: dict[str, str],
    admin_headers: dict[str, str],
) -> None:
    low = post_request(app_client, agent_headers, title="Low", blocked_tasks=1)
    high = post_request(app_client, agent_headers, title="High", blocked_tasks=3)

    body = app_client.get("/requests", headers=admin_headers).json()
    assert [item["id"] for item in body] == [high["id"], low["id"]]
    assert body[0]["score"] == 30
    assert body[1]["score"] == 10


def test_credential_outranks_a_busier_clarification(
    app_client: TestClient,
    agent_headers: dict[str, str],
    admin_headers: dict[str, str],
) -> None:
    clarification = post_request(
        app_client,
        agent_headers,
        request_type="clarification",
        title="Which env",
        blocked_tasks=2,
    )
    credential = post_request(
        app_client,
        agent_headers,
        request_type="credential",
        title="Need a token",
        blocked_tasks=0,
    )

    body = app_client.get("/requests", headers=admin_headers).json()
    assert [item["id"] for item in body] == [credential["id"], clarification["id"]]
    assert body[0]["score"] == 25
    assert body[1]["score"] == 20


def test_agent_reads_its_own_request_but_not_another_agents(
    app_client: TestClient,
    agent_headers: dict[str, str],
    other_agent_headers: dict[str, str],
) -> None:
    mine = post_request(app_client, agent_headers)

    assert app_client.get(f"/requests/{mine['id']}", headers=agent_headers).status_code == 200
    assert app_client.get(f"/requests/{mine['id']}", headers=other_agent_headers).status_code == 404


def test_admin_reads_any_request(
    app_client: TestClient,
    agent_headers: dict[str, str],
    admin_headers: dict[str, str],
) -> None:
    mine = post_request(app_client, agent_headers)
    response = app_client.get(f"/requests/{mine['id']}", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["id"] == mine["id"]


def test_mine_returns_only_the_calling_agents_requests(
    app_client: TestClient,
    agent_headers: dict[str, str],
    other_agent_headers: dict[str, str],
) -> None:
    mine = post_request(app_client, agent_headers)
    post_request(app_client, other_agent_headers, title="Theirs")

    body = app_client.get("/requests/mine", headers=agent_headers).json()
    assert [item["id"] for item in body] == [mine["id"]]


def test_admin_resolves_a_request_and_a_second_resolve_conflicts(
    app_client: TestClient,
    agent_headers: dict[str, str],
    admin_headers: dict[str, str],
) -> None:
    created = post_request(app_client, agent_headers)

    response = app_client.post(
        f"/requests/{created['id']}/resolve",
        json={"resolution": "Approved, ship it"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "resolved"
    assert body["resolution"] == "Approved, ship it"
    assert body["resolved_at"] is not None

    second = app_client.post(
        f"/requests/{created['id']}/resolve",
        json={"resolution": "Again"},
        headers=admin_headers,
    )
    assert second.status_code == 409


def test_resolve_of_unknown_request_returns_404(
    app_client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    response = app_client.post(
        "/requests/does-not-exist/resolve",
        json={"resolution": "nothing"},
        headers=admin_headers,
    )
    assert response.status_code == 404


def test_events_show_created_then_resolved_in_order(
    app_client: TestClient,
    agent_headers: dict[str, str],
    admin_headers: dict[str, str],
) -> None:
    created = post_request(app_client, agent_headers)
    app_client.post(
        f"/requests/{created['id']}/resolve",
        json={"resolution": "Approved"},
        headers=admin_headers,
    )

    response = app_client.get(f"/requests/{created['id']}/events", headers=agent_headers)
    assert response.status_code == 200
    events = response.json()
    assert [event["kind"] for event in events] == ["created", "resolved"]
    assert events[0]["payload"] is None
    assert events[1]["payload"] == {"resolution": "Approved"}


def test_events_are_hidden_from_another_agent(
    app_client: TestClient,
    agent_headers: dict[str, str],
    other_agent_headers: dict[str, str],
) -> None:
    created = post_request(app_client, agent_headers)
    response = app_client.get(f"/requests/{created['id']}/events", headers=other_agent_headers)
    assert response.status_code == 404


def test_status_filter_all_returns_open_and_resolved(
    app_client: TestClient,
    agent_headers: dict[str, str],
    admin_headers: dict[str, str],
) -> None:
    resolved = post_request(app_client, agent_headers, title="Resolved one")
    still_open = post_request(app_client, agent_headers, title="Open one")
    app_client.post(
        f"/requests/{resolved['id']}/resolve",
        json={"resolution": "Done"},
        headers=admin_headers,
    )

    open_only = app_client.get("/requests", headers=admin_headers).json()
    assert [item["id"] for item in open_only] == [still_open["id"]]

    resolved_only = app_client.get("/requests?status=resolved", headers=admin_headers).json()
    assert [item["id"] for item in resolved_only] == [resolved["id"]]

    every = app_client.get("/requests?status=all", headers=admin_headers).json()
    assert {item["id"] for item in every} == {resolved["id"], still_open["id"]}


def fetch_first(
    client: TestClient,
    headers: dict[str, str],
    status_filter: str,
) -> dict[str, object]:
    response = client.get(f"/requests?status={status_filter}", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    return body[0]


def test_resolved_score_freezes_while_open_scores_keep_rising(
    app_client: TestClient,
    agent_headers: dict[str, str],
    admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolved = post_request(app_client, agent_headers, title="Resolved one", blocked_tasks=2)
    post_request(app_client, agent_headers, title="Open one", blocked_tasks=2)
    app_client.post(
        f"/requests/{resolved['id']}/resolve",
        json={"resolution": "Done"},
        headers=admin_headers,
    )

    first_resolved = fetch_first(app_client, admin_headers, "resolved")
    first_open = fetch_first(app_client, admin_headers, "open")

    def five_hours_later() -> datetime:
        return datetime.now(UTC) + timedelta(hours=5)

    monkeypatch.setattr("board.routes.requests.utc_now", five_hours_later)

    second_resolved = fetch_first(app_client, admin_headers, "resolved")
    second_open = fetch_first(app_client, admin_headers, "open")

    assert second_resolved["score"] == first_resolved["score"]
    assert second_open["score"] > first_open["score"]
    assert second_open["score"] == first_open["score"] + 300


def test_invalid_status_filter_is_rejected(
    app_client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    response = app_client.get("/requests?status=bogus", headers=admin_headers)
    assert response.status_code == 422
