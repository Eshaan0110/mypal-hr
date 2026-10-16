"""Build published test policies through the real lifecycle code (approve -> publish -> index)."""

from datetime import date

from sqlalchemy.orm import Session

from mypal.db.models import (
    Company,
    EmployeeCategory,
    Location,
    PolicyVersion,
    PolicyVersionScope,
    PolicyVersionStatus,
)
from mypal.policies import lifecycle
from mypal.retrieval.index import VectorIndex
from tests.factories import REVIEWER, make_chunk, make_policy, make_version
from tests.fakes import HashEmbedder

TODAY = date(2026, 6, 1)


def seed_reference(session: Session) -> None:
    for model, codes in (
        (Company, ["CO-A", "CO-B"]),
        (Location, ["NORTH", "SOUTH"]),
        (EmployeeCategory, ["PERMANENT", "TRAINEE"]),
    ):
        for code in codes:
            if session.get(model, code) is None:
                session.add(model(code=code, name=f"Test {code}"))
    session.flush()


def add_version(
    session: Session,
    key: str,
    passages: list[tuple[str, str]],  # (section heading, text)
    *,
    label: str = "v1",
    company: str = "CO-A",
    location: str | None = None,
    category: str | None = None,
    status: PolicyVersionStatus = PolicyVersionStatus.APPROVED,
    effective_from: date = date(2026, 1, 1),
) -> PolicyVersion:
    from mypal.db.models import Policy

    policy = session.query(Policy).filter_by(policy_key=key).one_or_none() or make_policy(
        session, key
    )
    version = make_version(
        session, policy, label=label, status=status, effective_from=effective_from
    )
    session.add(
        PolicyVersionScope(
            version_id=version.id,
            company_code=company,
            location_code=location,
            category_code=category,
        )
    )
    for ordinal, (heading, text) in enumerate(passages):
        number = heading.split(" ", 1)[0].rstrip(".")
        make_chunk(
            session,
            version,
            ordinal=ordinal,
            text=text,
            heading_path=[heading],
            section_ref=number,
            page_start=1,
            page_end=1,
        )
    return version


def publish_version(
    session: Session, index: VectorIndex, version: PolicyVersion, today: date = TODAY
) -> PolicyVersion:
    return lifecycle.publish(session, version.id, REVIEWER, HashEmbedder(), index, today)


def published(session: Session, index: VectorIndex, key: str, passages, **kwargs) -> PolicyVersion:  # noqa: ANN001
    return publish_version(session, index, add_version(session, key, passages, **kwargs))
