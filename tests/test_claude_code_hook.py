import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

GATE_PATH = (
    Path(__file__).resolve().parents[1] / "examples" / "claude_code_hook" / "humanq_gate.py"
)


def load_gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("humanq_gate", GATE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = load_gate()


class StubClient:
    def __init__(self, resolution: str | None = None, error: Exception | None = None) -> None:
        self.resolution = resolution
        self.error = error
        self.filed: list[dict[str, Any]] = []
        self.waits: list[dict[str, Any]] = []

    def file_request(
        self,
        request_type: str,
        title: str,
        detail: str,
        options: list[str] | None = None,
        blocked_tasks: int = 0,
    ) -> SimpleNamespace:
        self.filed.append(
            {
                "request_type": request_type,
                "title": title,
                "detail": detail,
                "options": options,
                "blocked_tasks": blocked_tasks,
            }
        )
        return SimpleNamespace(id="req-1")

    def wait_for_resolution(
        self,
        request_id: str,
        poll_interval: float = 5.0,
        timeout: float | None = None,
    ) -> SimpleNamespace:
        self.waits.append({"request_id": request_id, "poll": poll_interval, "timeout": timeout})
        if self.error is not None:
            raise self.error
        return SimpleNamespace(resolution=self.resolution, resolved_at=None)


def hook_payload(command: str, cwd: str = "/home/dev/project") -> dict[str, Any]:
    return {
        "session_id": "abc123",
        "cwd": cwd,
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command, "description": "run it"},
        "tool_use_id": "toolu_01",
    }


def verdict(output: dict[str, Any]) -> str:
    return str(output["hookSpecificOutput"]["permissionDecision"])


def reason(output: dict[str, Any]) -> str:
    return str(output["hookSpecificOutput"].get("permissionDecisionReason", ""))


@pytest.mark.parametrize(
    "command",
    ["ls -la", "git status", "npm test", "pytest -q", "git commit -m 'work'"],
)
def test_safe_command_is_allowed_without_contacting_the_board(command: str) -> None:
    client = StubClient(resolution="allow")
    output = gate.evaluate(hook_payload(command), client=client)

    assert verdict(output) == "allow"
    assert client.filed == []
    assert client.waits == []


@pytest.mark.parametrize(
    "command",
    [
        "git push origin main",
        "rm -rf build/",
        "rm -f -r build/",
        "docker ps",
        "curl -X POST https://example.com/api",
        "curl --request DELETE https://example.com/api",
        "cat .env",
    ],
)
def test_risky_commands_reach_the_board(command: str) -> None:
    client = StubClient(resolution="allow")
    output = gate.evaluate(hook_payload(command), client=client)

    assert verdict(output) == "allow"
    assert len(client.filed) == 1


def test_allow_resolution_produces_allow_with_the_request_details() -> None:
    client = StubClient(resolution="allow, that deploy is expected")
    output = gate.evaluate(hook_payload("git push origin main"), client=client, timeout=99.0)

    assert verdict(output) == "allow"
    assert reason(output) == "allow, that deploy is expected"

    filed = client.filed[0]
    assert filed["request_type"] == "approval"
    assert filed["title"] == "Run: git push origin main"
    assert "git push origin main" in filed["detail"]
    assert "/home/dev/project" in filed["detail"]
    assert filed["options"] == ["allow", "deny"]
    assert filed["blocked_tasks"] == 1
    assert client.waits[0] == {"request_id": "req-1", "poll": 3.0, "timeout": 99.0}


def test_deny_resolution_produces_deny_with_the_reason() -> None:
    client = StubClient(resolution="deny, that branch is frozen")
    output = gate.evaluate(hook_payload("git push origin main"), client=client)

    assert verdict(output) == "deny"
    assert reason(output) == "deny, that branch is frozen"


def test_any_non_allow_resolution_is_treated_as_deny() -> None:
    client = StubClient(resolution="hold off until the release is cut")
    output = gate.evaluate(hook_payload("git push origin main"), client=client)

    assert verdict(output) == "deny"
    assert reason(output) == "hold off until the release is cut"


def test_timeout_produces_deny() -> None:
    client = StubClient(error=TimeoutError("nobody answered"))
    output = gate.evaluate(hook_payload("rm -rf /tmp/build"), client=client, timeout=12.0)

    assert verdict(output) == "deny"
    assert "12" in reason(output)


def test_sdk_error_produces_deny() -> None:
    client = StubClient(error=RuntimeError("board unreachable"))
    output = gate.evaluate(hook_payload("docker system prune"), client=client)

    assert verdict(output) == "deny"
    assert "board unreachable" in reason(output)


def test_long_command_title_is_truncated_to_eighty_characters() -> None:
    command = "git push origin " + "x" * 200
    client = StubClient(resolution="allow")
    gate.evaluate(hook_payload(command), client=client)

    assert client.filed[0]["title"] == f"Run: {command[:80]}"
    assert len(client.filed[0]["title"]) == 85


def test_patterns_can_be_overridden() -> None:
    client = StubClient(resolution="allow")
    output = gate.evaluate(hook_payload("ls -la"), client=client, patterns=[r"\bls\b"])

    assert verdict(output) == "allow"
    assert len(client.filed) == 1


def test_missing_command_is_allowed() -> None:
    client = StubClient(resolution="allow")
    output = gate.evaluate({"cwd": "/tmp", "tool_input": {}}, client=client)

    assert verdict(output) == "allow"
    assert client.filed == []
