"""The one-command demo load: the fictional sample policies end up in the state the evaluation
question sets expect, through the normal lifecycle (four-eyes, audit), and only once."""

from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from mypal.db.models import AuditEvent, Policy, PolicyVersion
from mypal.errors import AppError
from mypal.ingestion.demo_policies import REVIEWER, UPLOADER, load_demo_policies
from mypal.retrieval.index import VectorIndex
from tests.fakes import fake_retriever

SAMPLES = Path(__file__).resolve().parents[3] / "sample_data" / "policies"
TODAY = date(2026, 11, 3)


def statuses(session: Session) -> dict[str, str]:
    rows = session.execute(
        select(Policy.policy_key, PolicyVersion.version_label, PolicyVersion.status).join(
            PolicyVersion, PolicyVersion.policy_id == Policy.id
        )
    ).all()
    return {f"{key} {label}": status.value for key, label, status in rows}


def test_demo_load_publishes_the_samples_and_rolls_leave_back_to_v1(
    db_session: Session, vector_index: VectorIndex
) -> None:
    load_demo_policies(db_session, SAMPLES, fake_retriever(vector_index), TODAY)

    assert statuses(db_session) == {
        "leave-policy v1": "active",
        "leave-policy v2": "superseded",
        "travel-reimbursement-policy v1": "active",
        "salary-advance-policy v1": "active",
    }
    versions = db_session.scalars(select(PolicyVersion)).all()
    assert {(v.created_by, v.approved_by) for v in versions} == {(UPLOADER, REVIEWER)}
    restores = db_session.scalars(
        select(AuditEvent).where(AuditEvent.action == "policy_version.restore")
    ).all()
    assert len(restores) == 1


def test_demo_load_refuses_a_database_that_already_has_the_demo_policies(
    db_session: Session, vector_index: VectorIndex
) -> None:
    load_demo_policies(db_session, SAMPLES, fake_retriever(vector_index), TODAY)

    with pytest.raises(AppError) as error:
        load_demo_policies(db_session, SAMPLES, fake_retriever(vector_index), TODAY)
    assert error.value.code == "demo_already_loaded"


def test_demo_load_checks_every_file_before_storing_anything(
    db_session: Session, vector_index: VectorIndex, tmp_path: Path
) -> None:
    with pytest.raises(AppError) as error:
        load_demo_policies(db_session, tmp_path, fake_retriever(vector_index), TODAY)

    assert error.value.code == "demo_files_missing"
    assert statuses(db_session) == {}
