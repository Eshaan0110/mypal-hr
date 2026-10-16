"""Employee feedback on answers.

Privacy by design (decision 2026-10-16): this table has NO question text, NO answer text and NO
user identifier. It records only how an answer was rated and which policy versions it cited.
"""

import uuid
from datetime import datetime

from sqlalchemy import Index, String
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from mypal.db.base import Base, created_at, uuid_pk
from mypal.db.models.enums import AnswerOutcome, FeedbackRating, str_enum


class Feedback(Base):
    __tablename__ = "feedback"
    __table_args__ = (Index("ix_feedback_created_at", "created_at"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    # Identifies the response being rated; it is not stored anywhere else.
    answer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    rating: Mapped[FeedbackRating] = mapped_column(
        str_enum(FeedbackRating, "rating"), nullable=False
    )
    # A fixed reason chosen from a list (e.g. "outdated", "wrong_policy"), never free text.
    reason_code: Mapped[str | None] = mapped_column(String(32))
    outcome: Mapped[AnswerOutcome] = mapped_column(
        str_enum(AnswerOutcome, "outcome"), nullable=False
    )
    # Snapshot of the versions cited. Not FKs: arrays cannot hold FKs, and versions are never
    # deleted, so the IDs stay resolvable.
    cited_version_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list, server_default="{}"
    )
    created_at: Mapped[datetime] = created_at()
