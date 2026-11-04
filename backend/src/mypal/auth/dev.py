"""DEVELOPMENT STAND-IN FOR REAL LOGIN. Not authentication.

Until IT provides SSO (Azure AD), a caller chooses one of these predefined FICTIONAL test users
with the `X-Dev-User` header. The caller can only pick a user - it can never supply or change a
company, location or category - so scope filtering is exercised exactly as it will be with real
identities. Settings refuse to start in staging/production while this mode is configured.
"""

import json
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, Header, Request
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from mypal.auth.principal import HR_ADMIN, Principal
from mypal.errors import AppError

DEV_USER_HEADER = "X-Dev-User"

DEV_USERS: dict[str, Principal] = {
    p.subject: p
    for p in (
        Principal("dev-employee-north", "DEMO-HEALTH", "DEMO-NORTH", "PERMANENT"),
        Principal("dev-probationer-south", "DEMO-HEALTH", "DEMO-SOUTH", "PROBATION"),
        Principal("dev-trainee", "DEMO-HEALTH", None, "TRAINEE"),
        # Belongs to a different (fictional) company: must never see Demo Health policies.
        Principal("dev-other-company", "DEMO-OTHER", None, "PERMANENT"),
        # Two HR administrators, so the four-eyes rule (uploader != approver) can be exercised.
        Principal("dev-hr-admin", "DEMO-HEALTH", None, None, frozenset({HR_ADMIN})),
        Principal("dev-hr-reviewer", "DEMO-HEALTH", None, None, frozenset({HR_ADMIN})),
    )
}


class _DevUserIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str = Field(pattern=r"^dev-[a-z0-9-]{1,60}$")
    company_code: str = Field(pattern=r"^[A-Z0-9_-]{1,32}$")
    location_code: str | None = Field(default=None, pattern=r"^[A-Z0-9_-]{1,32}$")
    category_code: str | None = Field(default=None, pattern=r"^[A-Z0-9_-]{1,32}$")
    roles: list[Literal["hr_admin"]] = []


def load_dev_users(path: Path) -> dict[str, Principal]:
    """Read a development users file: a JSON list of users like the built-in ones.

    Used to log in to a separately loaded data set whose scope codes differ from the fictional
    samples. The file only lists test identities; like the built-ins, the caller can still only
    pick one of them, never set their attributes. Invalid files stop the app at startup.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        users = TypeAdapter(list[_DevUserIn]).validate_python(raw)
    except (OSError, ValueError) as exc:
        raise ValueError(f"Invalid development users file {path}: {exc}") from exc
    if not users:
        raise ValueError(f"Development users file {path} lists no users.")
    subjects = [u.subject for u in users]
    if len(set(subjects)) != len(subjects):
        raise ValueError(f"Development users file {path} repeats a subject.")
    return {
        u.subject: Principal(
            u.subject, u.company_code, u.location_code, u.category_code, frozenset(u.roles)
        )
        for u in users
    }


class NotAuthenticated(AppError):
    status_code = 401
    code = "not_authenticated"


async def get_principal(
    request: Request,
    dev_user: Annotated[str | None, Header(alias=DEV_USER_HEADER)] = None,
) -> Principal:
    if request.app.state.settings.auth_mode != "dev":  # pragma: no cover - only mode for now
        raise NotAuthenticated("No authentication method is configured.")
    users: dict[str, Principal] = request.app.state.dev_users
    if not dev_user:
        raise NotAuthenticated(
            f"Development mode: send the {DEV_USER_HEADER} header with one of: "
            f"{', '.join(sorted(users))}."
        )
    principal = users.get(dev_user)
    if principal is None:
        raise NotAuthenticated(f"Unknown development user '{dev_user[:64]}'.")
    return principal


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


class Forbidden(AppError):
    status_code = 403
    code = "forbidden"


async def require_hr_admin(principal: CurrentPrincipal) -> Principal:
    """Server-side gate for the HR administration API. Hiding the admin screens in the browser
    is only convenience; this check is what actually protects them."""
    if HR_ADMIN not in principal.roles:
        raise Forbidden("HR administration is restricted to HR administrators.")
    return principal


HrAdmin = Annotated[Principal, Depends(require_hr_admin)]
