"""Reference lists for policy scope: which companies, locations and employee categories exist.

Scope columns elsewhere are foreign keys into these tables, so a typo such as "MHK" vs "MHKA"
is rejected by the database instead of silently hiding (or exposing) a policy.
"""

from datetime import datetime

from sqlalchemy import CheckConstraint, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from mypal.db.base import Base, created_at

_CODE_FORMAT = "code ~ '^[A-Z0-9_-]{1,32}$'"


class Company(Base):
    __tablename__ = "companies"
    __table_args__ = (CheckConstraint(_CODE_FORMAT, name="code_format"),)

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = created_at()


class Location(Base):
    __tablename__ = "locations"
    __table_args__ = (CheckConstraint(_CODE_FORMAT, name="code_format"),)

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = created_at()


class EmployeeCategory(Base):
    __tablename__ = "employee_categories"
    __table_args__ = (CheckConstraint(_CODE_FORMAT, name="code_format"),)

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = created_at()
