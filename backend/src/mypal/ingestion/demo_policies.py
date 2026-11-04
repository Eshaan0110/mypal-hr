"""Load the FICTIONAL sample policies (sample_data/policies) into an empty development database,
through the normal lifecycle: upload as draft, submit, approve by a second person, publish.

The result is the state the evaluation question sets expect:
- leave-policy v1, travel-reimbursement-policy v1 and salary-advance-policy v1 active;
- leave-policy v2 published and then rolled back, so it is superseded (the replacement and
  rollback demonstration, and the "outdated figure" evaluation questions).

Development only. Real policies go through the HR admin portal.
"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from mypal.db.models import Policy
from mypal.errors import AppError
from mypal.ingestion.demo_reference import seed_demo_reference_data
from mypal.ingestion.schemas import DraftMetadata, ScopeInput
from mypal.ingestion.service import store_draft
from mypal.policies import lifecycle
from mypal.retrieval.retriever import Retriever

# The two fictional HR administrators of the development login, so the portal shows who did what.
UPLOADER, REVIEWER = "dev-hr-admin", "dev-hr-reviewer"
ROLLBACK_REASON = "Demonstration: v2 rolled back to v1"


@dataclass(frozen=True)
class DemoVersion:
    filename: str
    policy_key: str
    title: str
    owner: str
    version_label: str
    effective_from: date
    scopes: tuple[str, ...]


DEMO_VERSIONS = (
    DemoVersion(
        "leave-policy-v1.pdf",
        "leave-policy",
        "Leave Policy",
        "HR Operations (fictional)",
        "v1",
        date(2026, 1, 1),
        ("DEMO-HEALTH:*:PERMANENT", "DEMO-HEALTH:*:PROBATION", "DEMO-HEALTH:*:TRAINEE"),
    ),
    DemoVersion(
        "travel-reimbursement-policy-v1.docx",
        "travel-reimbursement-policy",
        "Travel and Reimbursement Policy",
        "Finance and HR (fictional)",
        "v1",
        date(2026, 2, 1),
        ("DEMO-HEALTH",),
    ),
    DemoVersion(
        "salary-advance-policy-v1.pdf",
        "salary-advance-policy",
        "Salary Advance Policy",
        "HR Operations (fictional)",
        "v1",
        date(2026, 3, 1),
        ("DEMO-HEALTH",),
    ),
    DemoVersion(
        "leave-policy-v2.pdf",
        "leave-policy",
        "Leave Policy",
        "HR Operations (fictional)",
        "v2",
        date(2026, 7, 1),
        ("DEMO-HEALTH:*:PERMANENT", "DEMO-HEALTH:*:PROBATION"),
    ),
)


def load_demo_policies(
    session: Session, folder: Path, retriever: Retriever, today: date
) -> list[str]:
    """Load every demo version and return one line per step. Refuses to touch a database that
    already holds any of the demo policies. The caller commits."""
    keys = {v.policy_key for v in DEMO_VERSIONS}
    if session.scalars(select(Policy.policy_key).where(Policy.policy_key.in_(keys))).first():
        raise AppError(
            "The demo policies are already loaded; nothing was changed.",
            code="demo_already_loaded",
            status_code=409,
        )
    missing = [v.filename for v in DEMO_VERSIONS if not (folder / v.filename).is_file()]
    if missing:
        raise AppError(
            f"Sample files not found in {folder}: {', '.join(missing)}",
            code="demo_files_missing",
            status_code=400,
        )

    seed_demo_reference_data(session)
    steps: list[str] = []
    versions = {}
    for demo in DEMO_VERSIONS:
        metadata = DraftMetadata(
            policy_key=demo.policy_key,
            title=demo.title,
            owner=demo.owner,
            version_label=demo.version_label,
            uploaded_by=UPLOADER,
            effective_from=demo.effective_from,
            scopes=[ScopeInput.parse(scope) for scope in demo.scopes],
        )
        content = (folder / demo.filename).read_bytes()
        version, _ = store_draft(session, metadata, demo.filename, content)
        lifecycle.submit_for_review(session, version.id, UPLOADER)
        lifecycle.approve(session, version.id, REVIEWER)
        lifecycle.publish(session, version.id, REVIEWER, retriever, today)
        versions[(demo.policy_key, demo.version_label)] = version
        steps.append(f"{demo.policy_key} {demo.version_label}: published")

    lifecycle.restore(
        session, versions[("leave-policy", "v1")].id, UPLOADER, ROLLBACK_REASON, retriever
    )
    steps.append("leave-policy v1: restored (v2 is now superseded)")
    return steps
