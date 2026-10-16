"""The scope resolver - the security gate in front of retrieval.

Postgres decides which policy versions an asker may see; the vector index is only ever searched
inside that list. A version qualifies only if ALL of these hold:

- it is ACTIVE (drafts, approved-but-unpublished and superseded versions never qualify);
- it is already in effect (effective_from is today or earlier);
- one of its scope rows matches the asker's company, and its location and category either
  match the asker's or are "all" (NULL).

When the asker's location or category is unknown, only "all" rows match. That is deliberately
conservative: an unknown attribute never unlocks a location- or category-specific policy.
"""

import uuid
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from mypal.auth.principal import Principal
from mypal.db.models import PolicyVersion, PolicyVersionScope, PolicyVersionStatus


def allowed_version_ids(session: Session, principal: Principal, today: date) -> list[uuid.UUID]:
    scope = PolicyVersionScope
    statement = (
        select(PolicyVersion.id)
        .join(scope, scope.version_id == PolicyVersion.id)
        .where(
            PolicyVersion.status == PolicyVersionStatus.ACTIVE,
            PolicyVersion.effective_from <= today,
            scope.company_code == principal.company_code,
            or_(scope.location_code.is_(None), scope.location_code == principal.location_code),
            or_(scope.category_code.is_(None), scope.category_code == principal.category_code),
        )
        .distinct()
    )
    return list(session.scalars(statement))
