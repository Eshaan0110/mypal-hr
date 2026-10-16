"""Designated HR contact routes shown in referrals. Values must come from HR - never invented."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, String, Text, false, true
from sqlalchemy.orm import Mapped, mapped_column

from mypal.db.base import Base, created_at, uuid_pk


class HrContact(Base):
    __tablename__ = "hr_contacts"
    __table_args__ = (CheckConstraint("length(btrim(route)) > 0", name="route_not_blank"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    company_code: Mapped[str] = mapped_column(
        String(32), ForeignKey("companies.code"), nullable=False
    )
    # NULL = applies to every location in the company.
    location_code: Mapped[str | None] = mapped_column(String(32), ForeignKey("locations.code"))
    # NULL = general HR contact; otherwise a topic such as "grievance".
    topic: Mapped[str | None] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(Text, nullable=False)  # e.g. "HR Business Partner"
    route: Mapped[str] = mapped_column(Text, nullable=False)  # email address, URL or phone
    # Confidential routes are used for sensitive matters (grievances, harassment).
    is_confidential: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    created_at: Mapped[datetime] = created_at()
