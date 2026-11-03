"""HR administration API: upload, preview, review, approve, publish and restore policy versions.

Every route requires the HR administrator role (checked on the server by `HrAdmin`). Who did
what comes from the logged-in identity, never from the request body, and every change is written
to the append-only audit trail by the lifecycle functions.
"""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from pydantic import ValidationError

from mypal.api.chat import get_today
from mypal.auth.dev import HrAdmin
from mypal.db.session import DbSession
from mypal.errors import AppError
from mypal.ingestion.file_checks import MAX_FILE_BYTES
from mypal.ingestion.schemas import DraftMetadata, ScopeInput
from mypal.ingestion.service import store_draft
from mypal.observability.request_id import get_request_id
from mypal.policies import lifecycle
from mypal.policies.register import list_policies, reference_data, version_detail
from mypal.retrieval.retriever import Retriever
from mypal.schemas.admin import PolicySummary, ReasonRequest, ReferenceData, VersionDetail
from mypal.schemas.errors import ErrorResponse

router = APIRouter(
    prefix="/admin",
    tags=["hr-admin"],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)


def get_retriever(request: Request) -> Retriever:
    return request.app.state.answer_dependencies.retriever


RetrieverDep = Annotated[Retriever, Depends(get_retriever)]
Today = Annotated[date, Depends(get_today)]


@router.get("/policies", response_model=list[PolicySummary])
def policies(_: HrAdmin, session: DbSession) -> list[PolicySummary]:
    """Every policy and all of its versions, in every status."""
    return list_policies(session)


@router.get("/reference", response_model=ReferenceData)
def reference(_: HrAdmin, session: DbSession) -> ReferenceData:
    """Scope codes (companies, locations, employee categories) for the upload form."""
    return reference_data(session)


@router.post(
    "/versions",
    response_model=VersionDetail,
    status_code=201,
    responses={409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
def upload(
    admin: HrAdmin,
    session: DbSession,
    file: Annotated[UploadFile, File(description="PDF or Word (.docx) policy document")],
    policy_key: Annotated[str, Form()],
    title: Annotated[str, Form()],
    owner: Annotated[str, Form()],
    version_label: Annotated[str, Form()],
    effective_from: Annotated[date, Form()],
    scope: Annotated[list[str], Form(description="COMPANY[:LOCATION[:CATEGORY]], '*' = all")],
    source_link: Annotated[str | None, Form()] = None,
) -> VersionDetail:
    """Parse the file and store it as a DRAFT. Nothing is visible to employees until the
    version is reviewed, approved and published."""
    try:
        metadata = DraftMetadata(
            policy_key=policy_key.strip(),
            title=title,
            owner=owner,
            version_label=version_label.strip(),
            uploaded_by=admin.subject,  # from the login, never from the form
            effective_from=effective_from,
            source_link=source_link or None,
            scopes=[ScopeInput.parse(value) for value in scope],
        )
    except (ValidationError, ValueError) as exc:
        raise AppError(_validation_message(exc), code="validation_error", status_code=422) from exc

    # Read at most one byte more than the limit, so an oversized upload is rejected without
    # holding the whole file in memory.
    content = file.file.read(MAX_FILE_BYTES + 1)
    version, _ = store_draft(
        session, metadata, file.filename or "upload", content, request_id=get_request_id()
    )
    session.commit()
    return version_detail(session, version.id)


@router.get("/versions/{version_id}", response_model=VersionDetail)
def detail(version_id: uuid.UUID, _: HrAdmin, session: DbSession) -> VersionDetail:
    """Parsed-document preview: metadata, quality report, every chunk, and the audit history."""
    return version_detail(session, version_id)


@router.post("/versions/{version_id}/submit", response_model=VersionDetail)
def submit(version_id: uuid.UUID, admin: HrAdmin, session: DbSession) -> VersionDetail:
    lifecycle.submit_for_review(session, version_id, admin.subject, get_request_id())
    session.commit()
    return version_detail(session, version_id)


@router.post("/versions/{version_id}/approve", response_model=VersionDetail)
def approve(version_id: uuid.UUID, admin: HrAdmin, session: DbSession) -> VersionDetail:
    lifecycle.approve(session, version_id, admin.subject, get_request_id())
    session.commit()
    return version_detail(session, version_id)


@router.post("/versions/{version_id}/reject", response_model=VersionDetail)
def reject(
    version_id: uuid.UUID, body: ReasonRequest, admin: HrAdmin, session: DbSession
) -> VersionDetail:
    lifecycle.reject(session, version_id, admin.subject, body.reason, get_request_id())
    session.commit()
    return version_detail(session, version_id)


@router.post("/versions/{version_id}/publish", response_model=VersionDetail)
def publish(
    version_id: uuid.UUID,
    admin: HrAdmin,
    session: DbSession,
    retriever: RetrieverDep,
    today: Today,
) -> VersionDetail:
    """Index the version, then make it the active one (the previous active version becomes
    superseded) in a single transaction."""
    lifecycle.publish(session, version_id, admin.subject, retriever, today, get_request_id())
    session.commit()
    return version_detail(session, version_id)


@router.post("/versions/{version_id}/restore", response_model=VersionDetail)
def restore(
    version_id: uuid.UUID,
    body: ReasonRequest,
    admin: HrAdmin,
    session: DbSession,
    retriever: RetrieverDep,
) -> VersionDetail:
    """Rollback: put a superseded version back in effect, with a reason for the audit trail."""
    lifecycle.restore(session, version_id, admin.subject, body.reason, retriever, get_request_id())
    session.commit()
    return version_detail(session, version_id)


def _validation_message(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        first = exc.errors()[0]
        field = ".".join(str(part) for part in first["loc"]) or "input"
        return f"Invalid {field}: {first['msg']}."
    return f"Invalid input: {exc}."
