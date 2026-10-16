from sqlalchemy.orm import Session

from mypal.db.models import Location, PolicyVersionScope
from tests.factories import (
    assert_violates,
    build_chunk,
    make_chunk,
    make_company,
    make_policy,
    make_version,
)


def test_scope_must_reference_a_known_company(db_session: Session) -> None:
    version = make_version(db_session, make_policy(db_session))
    scope = PolicyVersionScope(version_id=version.id, company_code="NO-SUCH-CO")

    assert_violates(db_session, "fk_policy_version_scopes_company_code_companies", scope)


def test_identical_all_locations_scope_cannot_repeat(db_session: Session) -> None:
    """NULL means "all"; NULLS NOT DISTINCT stops the same "all" row being added twice."""
    company = make_company(db_session)
    version = make_version(db_session, make_policy(db_session))
    db_session.add(PolicyVersionScope(version_id=version.id, company_code=company.code))
    db_session.flush()

    duplicate = PolicyVersionScope(version_id=version.id, company_code=company.code)

    assert_violates(db_session, "uq_policy_version_scopes_combination", duplicate)


def test_version_can_target_several_locations(db_session: Session) -> None:
    company = make_company(db_session)
    db_session.add_all([Location(code="LOC-A", name="Test A"), Location(code="LOC-B", name="B")])
    version = make_version(db_session, make_policy(db_session))
    db_session.add_all(
        [
            PolicyVersionScope(version_id=version.id, company_code=company.code, location_code=c)
            for c in ("LOC-A", "LOC-B")
        ]
    )
    db_session.flush()

    db_session.refresh(version)
    assert {s.location_code for s in version.scopes} == {"LOC-A", "LOC-B"}


def test_reference_codes_must_be_upper_case(db_session: Session) -> None:
    assert_violates(db_session, "ck_locations_code_format", Location(code="bad code", name="x"))


def test_chunk_page_range_must_be_ordered(db_session: Session) -> None:
    version = make_version(db_session, make_policy(db_session))

    chunk = build_chunk(version, page_start=5, page_end=3)

    assert_violates(db_session, "ck_chunks_page_range_valid", chunk)


def test_chunk_text_cannot_be_blank(db_session: Session) -> None:
    version = make_version(db_session, make_policy(db_session))

    assert_violates(db_session, "ck_chunks_text_not_blank", build_chunk(version, text="   "))


def test_chunks_keep_heading_path_and_order(db_session: Session) -> None:
    version = make_version(db_session, make_policy(db_session))
    make_chunk(db_session, version, ordinal=1, heading_path=["4 Leave", "4.2 Casual leave"])
    make_chunk(db_session, version, ordinal=0)

    db_session.refresh(version)
    assert [c.ordinal for c in version.chunks] == [0, 1]
    assert version.chunks[1].heading_path == ["4 Leave", "4.2 Casual leave"]
