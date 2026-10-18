"""Recording feedback.

The browser sends only: which answer (answer_id), helpful or not, and optionally a reason chosen
from a fixed list. Everything else - the answer's outcome and which policy versions it cited - is
taken from the server's own record of that answer (query_metrics), so feedback cannot be forged
for answers that never happened or attributed to policies that were never cited.

Nothing about the person is stored. The endpoint requires a login only so that anonymous
traffic cannot flood the table.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from mypal.db.models import Feedback, FeedbackRating, QueryMetric
from mypal.errors import AppError


def record_feedback(
    session: Session,
    answer_id: uuid.UUID,
    rating: FeedbackRating,
    reason_code: str | None,
) -> Feedback:
    answer = session.scalar(select(QueryMetric).where(QueryMetric.answer_id == answer_id))
    if answer is None:
        raise AppError("That answer could not be found.", code="unknown_answer", status_code=404)
    if rating is FeedbackRating.HELPFUL:
        reason_code = None  # reasons only explain "not helpful"

    feedback = session.scalar(select(Feedback).where(Feedback.answer_id == answer_id))
    if feedback is None:
        feedback = Feedback(answer_id=answer_id)
        session.add(feedback)
    # One rating per answer: a second submission is a change of mind, not a second vote.
    feedback.rating = rating
    feedback.reason_code = reason_code
    feedback.outcome = answer.outcome
    feedback.cited_version_ids = list(answer.cited_version_ids)
    session.commit()
    return feedback
