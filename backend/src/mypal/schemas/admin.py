"""Contracts for the HR administration API (/api/admin)."""

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from mypal.db.models import ChunkKind, PolicyVersionStatus


class VersionSummary(BaseModel):
    id: uuid.UUID
    version_label: str
    status: PolicyVersionStatus
    effective_from: date | None
    source_filename: str
    created_by: str
    created_at: datetime
    approved_by: str | None
    published_at: datetime | None


class PolicySummary(BaseModel):
    policy_key: str
    title: str
    owner: str
    versions: list[VersionSummary]  # newest first


class ScopeOut(BaseModel):
    company_code: str
    location_code: str | None  # None = all locations
    category_code: str | None  # None = all categories


class ChunkPreview(BaseModel):
    ordinal: int
    kind: ChunkKind
    heading_path: list[str]
    section_ref: str | None
    page_start: int | None
    page_end: int | None
    text: str


class AuditEntry(BaseModel):
    occurred_at: datetime
    actor_id: str
    action: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None


class VersionDetail(VersionSummary):
    policy_key: str
    policy_title: str
    policy_owner: str
    source_link: str | None
    supersedes_version_id: uuid.UUID | None
    scopes: list[ScopeOut]
    # The ingestion quality report: issues (info / warning / blocking) to check before approval.
    parse_report: dict[str, Any] | None
    chunks: list[ChunkPreview]
    history: list[AuditEntry]  # oldest first


class ReasonRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=1000)


class ReferenceCode(BaseModel):
    code: str
    name: str


class ReferenceData(BaseModel):
    """The scope codes HR can choose from when uploading."""

    companies: list[ReferenceCode]
    locations: list[ReferenceCode]
    categories: list[ReferenceCode]
