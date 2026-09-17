import json
import os
import re
import sys
from typing import Any

ALLOW = "allow"
DENY = "deny"
DEFAULT_TIMEOUT = 240.0
POLL_INTERVAL = 3.0

DEFAULT_PATTERNS = [
    r"\bgit\s+push\b",
    r"\brm\b(?=.*\s--?\w*r)(?=.*\s--?\w*f)",
    r"\bdocker\b",
    r"\bcurl\b(?=.*(?:-X|--request)\s*(?:POST|PUT|DELETE)\b)",
    r"\.env\b",
]


def load_patterns() -> list[str]:
    raw = os.environ.get("HUMANQ_GATE_PATTERNS")
    if not raw:
        return DEFAULT_PATTERNS
    try:
        parsed = json.loads(raw)
    except ValueError:
        return DEFAULT_PATTERNS
    if not isinstance(parsed, list):
        return DEFAULT_PATTERNS
    return [str(item) for item in parsed]


def gate_timeout() -> float:
    try:
        return float(os.environ.get("HUMANQ_GATE_TIMEOUT", DEFAULT_TIMEOUT))
    except ValueError:
        return DEFAULT_TIMEOUT


def first_match(command: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        try:
            if re.search(pattern, command):
                return pattern
        except re.error:
            continue
    return None


def decision(verdict: str, reason: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "hookEventName": "PreToolUse",
        "permissionDecision": verdict,
    }
    if reason:
        payload["permissionDecisionReason"] = reason
    return {"hookSpecificOutput": payload}


def make_client() -> Any:
    from humanq import Client

    return Client()


def evaluate(
    payload: dict[str, Any],
    client: Any | None = None,
    patterns: list[str] | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    tool_input = payload.get("tool_input") or {}
    command = str(tool_input.get("command") or "")
    if first_match(command, patterns if patterns is not None else load_patterns()) is None:
        return decision(ALLOW)

    limit = timeout if timeout is not None else gate_timeout()
    cwd = str(payload.get("cwd") or "")
    try:
        active = client if client is not None else make_client()
        request = active.file_request(
            "approval",
            f"Run: {command[:80]}",
            f"Command:\n{command}\n\nWorking directory:\n{cwd}",
            options=[ALLOW, DENY],
            blocked_tasks=1,
        )
        resolution = active.wait_for_resolution(
            request.id,
            poll_interval=POLL_INTERVAL,
            timeout=limit,
        )
    except TimeoutError:
        return decision(DENY, f"No human answered on the humanq board within {limit:g} seconds.")
    except Exception as error:
        return decision(DENY, f"The humanq gate could not reach the board: {error}")

    text = str(resolution.resolution or "").strip()
    if text.lower().startswith(ALLOW):
        return decision(ALLOW, text)
    return decision(DENY, text or "A human denied this command.")


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("hook payload was not an object")
        output = evaluate(payload)
    except BaseException as error:
        output = decision(DENY, f"The humanq gate failed to run: {error}")

    print(json.dumps(output))
    verdict = output["hookSpecificOutput"]["permissionDecision"]
    return 0 if verdict == ALLOW else 2


if __name__ == "__main__":
    sys.exit(main())
