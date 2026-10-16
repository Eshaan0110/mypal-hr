"""HR-approved fixed answers. Each FAQ is tied to the policy version (and chunks) it is based on,
so it can be flagged for review when that version is superseded."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from mypal.db.base import Base, created_at, uuid_pk
from mypal.db.models.enums import FaqStatus, str_enum


class Faq(Base):
    __tablename__ = "faqs"
    __table_args__ = (
        Index("ix_faqs_status", "status"),
        CheckConstraint("approved_by IS NULL OR approved_by <> created_by", name="four_eyes"),
        CheckConstraint(
            "(approved_by IS NULL) = (approved_at IS NULL)", name="approval_fields_together"
        ),
        CheckConstraint(
            "status <> 'active' OR approved_by IS NOT NULL", name="active_has_approver"
        ),
        CheckConstraint("length(btrim(question)) > 0", name="question_not_blank"),
        CheckConstraint("length(btrim(answer)) > 0", name="answer_not_blank"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    source_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("policy_versions.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[FaqStatus] = mapped_column(
        str_enum(FaqStatus, "status"),
        nullable=False,
        default=FaqStatus.DRAFT,
        server_default=FaqStatus.DRAFT.value,
    )
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = created_at()
    approved_by: Mapped[str | None] = mapped_column(Text)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FaqSource(Base):
    """Which chunks support an FAQ answer (a proper join table, so every link is a real FK)."""

    __tablename__ = "faq_sources"

    faq_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("faqs.id", ondelete="CASCADE"), primary_key=True
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chunks.id", ondelete="RESTRICT"), primary_key=True
    )
