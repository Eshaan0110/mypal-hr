from collections.abc import AsyncIterator
from datetime import date
from typing import Annotated

import anyio
from fastapi import APIRouter, Depends, Request

from mypal.answering.service import AnswerDependencies, answer_question
from mypal.auth.dev import CurrentPrincipal
from mypal.db.session import DbSession
from mypal.errors import AppError
from mypal.observability.request_id import get_request_id
from mypal.schemas.chat import ChatRequest, ChatResponse
from mypal.schemas.errors import ErrorResponse

router = APIRouter(tags=["chat"])


async def get_answer_dependencies(request: Request) -> AnswerDependencies:
    return request.app.state.answer_dependencies


async def get_today() -> date:
    """Injected so tests can control "today" (effective dates)."""
    return date.today()


async def chat_slot(request: Request) -> AsyncIterator[None]:
    """Wait (on the event loop, holding no thread or connection) for one of the
    `chat_max_concurrent` answering slots. Found by stress testing: 60 simultaneous questions
    each held a worker thread for up to 11 minutes and starved every other request."""
    settings = request.app.state.settings
    state = request.app.state
    if getattr(state, "chat_slots", None) is None:  # created on the event loop, on first use
        state.chat_slots = anyio.Semaphore(settings.chat_max_concurrent)
    slots: anyio.Semaphore = state.chat_slots
    try:
        with anyio.fail_after(settings.chat_queue_timeout_seconds):
            await slots.acquire()
    except TimeoutError:
        raise AppError(
            "My Pal is answering many questions right now. Please try again in a minute.",
            code="server_busy",
            status_code=503,
        ) from None
    try:
        yield
    finally:
        slots.release()


@router.post(
    "/chat",
    response_model=ChatResponse,
    responses={
        401: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
def chat(
    _slot: Annotated[None, Depends(chat_slot)],  # first: wait before anything else is opened
    body: ChatRequest,
    principal: CurrentPrincipal,
    session: DbSession,
    deps: Annotated[AnswerDependencies, Depends(get_answer_dependencies)],
    today: Annotated[date, Depends(get_today)],
) -> ChatResponse:
    """Ask one HR policy question. Returns an answer with citations, a clarification question,
    or a referral to HR. A plain `def` route: FastAPI runs it in a worker thread, so the slow
    model call does not block other requests."""
    if len(body.message) > deps.settings.question_max_chars:
        raise AppError(
            f"Questions are limited to {deps.settings.question_max_chars} characters.",
            code="question_too_long",
            status_code=422,
        )
    return answer_question(session, deps, principal, body.message, today, get_request_id())
