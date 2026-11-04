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
from sqlalchemy.dialects.postgresql import insert
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

    # One rating per answer: a second submission is a change of mind, not a second vote. A single
    # INSERT ... ON CONFLICT is atomic, so simultaneous submissions (a double click, two tabs)
    # cannot both try to insert and trip the unique constraint.
    values = {
        "rating": rating,
        "reason_code": reason_code,
        "outcome": answer.outcome,
        "cited_version_ids": list(answer.cited_version_ids),
    }
    statement = (
        insert(Feedback)
        .values(answer_id=answer_id, **values)
        .on_conflict_do_update(index_elements=[Feedback.answer_id], set_=values)
        .returning(Feedback)
    )
    feedback = session.scalars(statement, execution_options={"populate_existing": True}).one()
    session.commit()
    return feedback
