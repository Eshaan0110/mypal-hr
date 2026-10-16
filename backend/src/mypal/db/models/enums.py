"""Fixed value sets used by database columns.

They are stored as VARCHAR plus a CHECK constraint rather than native Postgres ENUM types:
native enums are awkward to change in migrations (values cannot easily be removed or renamed).
"""

from enum import StrEnum

from sqlalchemy import Enum


class PolicyVersionStatus(StrEnum):
    DRAFT = "draft"  # uploaded and parsed; editable
    IN_REVIEW = "in_review"  # submitted to a reviewer
    APPROVED = "approved"  # signed off, not yet published
    ACTIVE = "active"  # the current version employees get answers from
    SUPERSEDED = "superseded"  # replaced by a newer version; kept for history and rollback
    REJECTED = "rejected"  # reviewer declined it


class ChunkKind(StrEnum):
    TEXT = "text"
    TABLE = "table"


class FaqStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    NEEDS_REVIEW = "needs_review"  # its source policy version was superseded
    RETIRED = "retired"


class FeedbackRating(StrEnum):
    HELPFUL = "helpful"
    NOT_HELPFUL = "not_helpful"


class AnswerOutcome(StrEnum):
    ANSWERED = "answered"  # generated from retrieved policy passages
    FAQ = "faq"  # an HR-approved fixed answer
    CLARIFICATION = "clarification"  # asked the employee a follow-up question
    REFERRAL = "referral"  # sent to the designated HR contact


def str_enum(enum_cls: type[StrEnum], name: str) -> Enum:
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda members: [m.value for m in members],
    )
