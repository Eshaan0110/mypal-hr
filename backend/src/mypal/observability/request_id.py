"""Request IDs: one identifier per HTTP request, attached to every log line and the response.

If a caller (e.g. a gateway) sends a well-formed X-Request-ID we reuse it so logs can be
correlated across systems; otherwise we generate one. Malformed values are replaced, never
echoed, so a client cannot inject arbitrary text into our logs.
"""

import logging
import re
import time
import uuid
from contextvars import ContextVar

from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)

logger = logging.getLogger("mypal.request")


def get_request_id() -> str | None:
    return _request_id.get()


def _choose_request_id(incoming: str | None) -> str:
    if incoming and _VALID_REQUEST_ID.fullmatch(incoming):
        return incoming
    return uuid.uuid4().hex


class RequestIdMiddleware:
    """Pure ASGI middleware (rather than BaseHTTPMiddleware) so the context variable is set in
    the same context that route handlers and exception handlers run in."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        incoming = headers.get(REQUEST_ID_HEADER.lower().encode("latin-1"))
        request_id = _choose_request_id(incoming.decode("latin-1") if incoming else None)

        # Also stored on the scope so the outermost 500 handler can read it via request.state.
        scope.setdefault("state", {})["request_id"] = request_id
        token = _request_id.set(request_id)
        started = time.perf_counter()
        status_code = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                message.setdefault("headers", [])
                message["headers"].append(
                    (REQUEST_ID_HEADER.lower().encode("latin-1"), request_id.encode("latin-1"))
                )
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            # Path only - query strings are not logged because they may contain user input.
            logger.info(
                "request completed",
                extra={
                    "method": scope["method"],
                    "path": scope["path"],
                    "status_code": status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                },
            )
            _request_id.reset(token)
