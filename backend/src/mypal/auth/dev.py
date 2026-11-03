"""DEVELOPMENT STAND-IN FOR REAL LOGIN. Not authentication.

Until IT provides SSO (Azure AD), a caller chooses one of these predefined FICTIONAL test users
with the `X-Dev-User` header. The caller can only pick a user - it can never supply or change a
company, location or category - so scope filtering is exercised exactly as it will be with real
identities. Settings refuse to start in staging/production while this mode is configured.
"""

from typing import Annotated

from fastapi import Depends, Header, Request

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


class NotAuthenticated(AppError):
    status_code = 401
    code = "not_authenticated"


def get_principal(
    request: Request,
    dev_user: Annotated[str | None, Header(alias=DEV_USER_HEADER)] = None,
) -> Principal:
    if request.app.state.settings.auth_mode != "dev":  # pragma: no cover - only mode for now
        raise NotAuthenticated("No authentication method is configured.")
    if not dev_user:
        raise NotAuthenticated(
            f"Development mode: send the {DEV_USER_HEADER} header with one of: "
            f"{', '.join(sorted(DEV_USERS))}."
        )
    principal = DEV_USERS.get(dev_user)
    if principal is None:
        raise NotAuthenticated(f"Unknown development user '{dev_user[:64]}'.")
    return principal


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


class Forbidden(AppError):
    status_code = 403
    code = "forbidden"


def require_hr_admin(principal: CurrentPrincipal) -> Principal:
    """Server-side gate for the HR administration API. Hiding the admin screens in the browser
    is only convenience; this check is what actually protects them."""
    if HR_ADMIN not in principal.roles:
        raise Forbidden("HR administration is restricted to HR administrators.")
    return principal


HrAdmin = Annotated[Principal, Depends(require_hr_admin)]
