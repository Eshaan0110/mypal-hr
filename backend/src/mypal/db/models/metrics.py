"""Per-question performance and cost figures, for the cost-per-query view in the plan.
Contains no question text, no answer text and no user identifier.

answer_id and cited_version_ids let feedback refer to a real answer: the feedback endpoint takes
the outcome and the cited versions from here instead of trusting what the browser sends.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, CheckConstraint, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from mypal.db.base import Base, created_at
from mypal.db.models.enums import AnswerOutcome, str_enum


class QueryMetric(Base):
    __tablename__ = "query_metrics"
    __table_args__ = (
        Index("ix_query_metrics_created_at", "created_at"),
        CheckConstraint("total_ms >= 0", name="total_ms_non_negative"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # NULL only for rows recorded before answers had ids (Phase 4).
    answer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), unique=True)
    cited_version_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list, server_default="{}"
    )
    outcome: Mapped[AnswerOutcome] = mapped_column(
        str_enum(AnswerOutcome, "outcome"), nullable=False
    )
    total_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    retrieval_ms: Mapped[int | None] = mapped_column(Integer)
    generation_ms: Mapped[int | None] = mapped_column(Integer)
    model: Mapped[str | None] = mapped_column(Text)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    # Estimated cost in the provider's billing currency; NULL when no LLM call was made.
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    top_retrieval_score: Mapped[float | None] = mapped_column()
    created_at: Mapped[datetime] = created_at()
