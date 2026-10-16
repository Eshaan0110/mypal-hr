"""Error conventions.

- Business logic raises AppError (or a subclass) with a stable machine-readable `code`.
- FastAPI/Starlette errors (404, 405, validation) are converted into the same envelope.
- Unexpected exceptions are logged with a traceback but the client only sees a generic message,
  so internal details (SQL, file paths, provider errors) never leak.
"""

import logging
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from mypal.observability.request_id import REQUEST_ID_HEADER
from mypal.schemas.errors import ErrorDetail, ErrorResponse

logger = logging.getLogger(__name__)

_HTTP_STATUS_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    429: "rate_limited",
}


class AppError(Exception):
    """Base class for errors we raise deliberately and want to show to the client."""

    status_code: int = 400
    code: str = "bad_request"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        self.details = details


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    request_id = _request_id(request)
    body = ErrorResponse(
        error=ErrorDetail(code=code, message=message, request_id=request_id, details=details)
    )
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(body, exclude_none=True),
        headers=headers,
    )


async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    return error_response(request, exc.status_code, exc.code, exc.message, exc.details)


async def _handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = _HTTP_STATUS_CODES.get(exc.status_code, "http_error")
    message = exc.detail if isinstance(exc.detail, str) else HTTPStatus(exc.status_code).phrase
    return error_response(request, exc.status_code, code, message, headers=exc.headers)


async def _handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    # The submitted value ("input") is deliberately dropped: it may contain personal details.
    details = [
        {"loc": list(err.get("loc", ())), "msg": err.get("msg", ""), "type": err.get("type", "")}
        for err in exc.errors()
    ]
    return error_response(
        request, 422, "validation_error", "The request is invalid.", details=details
    )


async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled error")
    request_id = _request_id(request)
    # This handler runs outside RequestIdMiddleware, so add the header here.
    headers = {REQUEST_ID_HEADER: request_id} if request_id else None
    return error_response(
        request, 500, "internal_error", "An unexpected error occurred.", headers=headers
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(Exception, _handle_unexpected_error)
