from fastapi import APIRouter

from mypal.auth.dev import CurrentPrincipal
from mypal.db.session import DbSession
from mypal.feedback.service import record_feedback
from mypal.schemas.errors import ErrorResponse
from mypal.schemas.feedback import FeedbackRequest, FeedbackResponse

router = APIRouter(tags=["feedback"])


@router.post(
    "/feedback",
    response_model=FeedbackResponse,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def submit_feedback(
    body: FeedbackRequest,
    _principal: CurrentPrincipal,  # login required; the identity is deliberately not stored
    session: DbSession,
) -> FeedbackResponse:
    record_feedback(session, body.answer_id, body.rating, body.reason_code)
    return FeedbackResponse(status="recorded")
