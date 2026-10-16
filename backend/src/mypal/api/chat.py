from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from mypal.answering.service import AnswerDependencies, answer_question
from mypal.auth.dev import CurrentPrincipal
from mypal.db.session import DbSession
from mypal.errors import AppError
from mypal.observability.request_id import get_request_id
from mypal.schemas.chat import ChatRequest, ChatResponse
from mypal.schemas.errors import ErrorResponse

router = APIRouter(tags=["chat"])


def get_answer_dependencies(request: Request) -> AnswerDependencies:
    return request.app.state.answer_dependencies


def get_today() -> date:
    """Injected so tests can control "today" (effective dates)."""
    return date.today()


@router.post(
    "/chat",
    response_model=ChatResponse,
    responses={401: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
def chat(
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
