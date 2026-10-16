"""Importing this package registers every model on Base.metadata (Alembic relies on that)."""

from mypal.db.models.audit import AuditEvent
from mypal.db.models.contact import HrContact
from mypal.db.models.enums import (
    AnswerOutcome,
    ChunkKind,
    FaqStatus,
    FeedbackRating,
    PolicyVersionStatus,
)
from mypal.db.models.faq import Faq, FaqSource
from mypal.db.models.feedback import Feedback
from mypal.db.models.metrics import QueryMetric
from mypal.db.models.policy import Chunk, Policy, PolicyVersion, PolicyVersionScope
from mypal.db.models.reference import Company, EmployeeCategory, Location

__all__ = [
    "AnswerOutcome",
    "AuditEvent",
    "Chunk",
    "ChunkKind",
    "Company",
    "EmployeeCategory",
    "Faq",
    "FaqSource",
    "FaqStatus",
    "Feedback",
    "FeedbackRating",
    "HrContact",
    "Location",
    "Policy",
    "PolicyVersion",
    "PolicyVersionScope",
    "PolicyVersionStatus",
    "QueryMetric",
]
