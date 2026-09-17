import os
import time
from collections.abc import Callable
from datetime import datetime
from types import TracebackType
from typing import Any

import httpx

from humanq.errors import HumanqError
from humanq.types import Request, RequestType, Resolution

URL_ENV = "HUMANQ_URL"
KEY_ENV = "HUMANQ_API_KEY"


def parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


def to_request(payload: dict[str, Any]) -> Request:
    created_at = parse_datetime(payload["created_at"])
    if created_at is None:
        raise HumanqError("The board returned a request without created_at")
    return Request(
        id=payload["id"],
        agent_id=payload["agent_id"],
        agent_name=payload["agent_name"],
        request_type=RequestType(payload["request_type"]),
        title=payload["title"],
        detail=payload["detail"],
        options=payload["options"],
        blocked_tasks=payload["blocked_tasks"],
        status=payload["status"],
        resolution=payload["resolution"],
        score=payload["score"],
        created_at=created_at,
        resolved_at=parse_datetime(payload["resolved_at"]),
    )


def error_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text
    if isinstance(body, dict) and "detail" in body:
        return str(body["detail"])
    return response.text


class Client:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        resolved_url = base_url or os.environ.get(URL_ENV)
        if not resolved_url:
            raise HumanqError(f"No board URL. Pass base_url or set {URL_ENV}.")
        resolved_key = api_key or os.environ.get(KEY_ENV)
        if not resolved_key:
            raise HumanqError(f"No API key. Pass api_key or set {KEY_ENV}.")
        self.base_url = resolved_url.rstrip("/")
        self.http = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            transport=transport,
            headers={"Authorization": f"Bearer {resolved_key}"},
        )

    def __enter__(self) -> "Client":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self.http.close()

    def payload_or_raise(self, response: httpx.Response) -> dict[str, Any]:
        if response.status_code // 100 != 2:
            detail = error_detail(response)
            raise HumanqError(
                f"The board returned {response.status_code}: {detail}",
                status=response.status_code,
                detail=detail,
            )
        body: dict[str, Any] = response.json()
        return body

    def file_request(
        self,
        request_type: RequestType | str,
        title: str,
        detail: str,
        options: list[str] | None = None,
        blocked_tasks: int = 0,
    ) -> Request:
        response = self.http.post(
            "/requests",
            json={
                "request_type": RequestType(request_type).value,
                "title": title,
                "detail": detail,
                "options": options,
                "blocked_tasks": blocked_tasks,
            },
        )
        return to_request(self.payload_or_raise(response))

    def get_request(self, request_id: str) -> Request:
        response = self.http.get(f"/requests/{request_id}")
        return to_request(self.payload_or_raise(response))

    def wait_for_resolution(
        self,
        request_id: str,
        poll_interval: float = 5.0,
        timeout: float | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> Resolution:
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            request = self.get_request(request_id)
            if request.status == "resolved":
                return Resolution(
                    request_id=request.id,
                    resolution=request.resolution or "",
                    resolved_at=request.resolved_at,
                )
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError(
                    f"Request {request_id} was not resolved within {timeout} seconds"
                )
            sleep(poll_interval)

    def ask(
        self,
        request_type: RequestType | str,
        title: str,
        detail: str,
        options: list[str] | None = None,
        blocked_tasks: int = 0,
        poll_interval: float = 5.0,
        timeout: float | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> Resolution:
        request = self.file_request(
            request_type=request_type,
            title=title,
            detail=detail,
            options=options,
            blocked_tasks=blocked_tasks,
        )
        return self.wait_for_resolution(
            request.id,
            poll_interval=poll_interval,
            timeout=timeout,
            sleep=sleep,
        )
