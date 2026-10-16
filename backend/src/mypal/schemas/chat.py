"""Request and response contract for asking My Pal a question."""

import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from mypal.db.models import AnswerOutcome

ReferralReason = Literal[
    "personal_records",  # balances, payslips: data the system does not have
    "sensitive_topic",  # grievances etc.: confidential route
    "no_applicable_policy",  # no published policy applies to this employee
    "insufficient_evidence",  # nothing relevant enough was found
    "not_in_policy",  # the model found the passages do not answer it
    "validation_failed",  # the model's answer failed the grounding checks
    "generation_unavailable",  # the language model could not be reached
]


class ChatRequest(BaseModel):
    # Only the question. Who is asking (company, location, category) comes from the login,
    # never from the request body.
    message: str = Field(min_length=1)


class Citation(BaseModel):
    """Built from the database, never from model output."""

    chunk_id: uuid.UUID
    policy_key: str
    policy_title: str
    version_label: str
    section: str | None
    heading_path: list[str]
    page_start: int | None
    page_end: int | None
    effective_from: date | None
    source_link: str | None


class HrContact(BaseModel):
    label: str
    route: str
    is_confidential: bool


class ChatResponse(BaseModel):
    answer_id: uuid.UUID  # identifies this response for feedback; not stored with any text
    outcome: AnswerOutcome
    message: str
    citations: list[Citation] = Field(default_factory=list)
    referral_reason: ReferralReason | None = None
    hr_contact: HrContact | None = None
