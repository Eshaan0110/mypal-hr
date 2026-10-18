from fastapi import APIRouter, Request

from mypal.auth.dev import DEV_USERS, CurrentPrincipal
from mypal.errors import AppError
from mypal.schemas.me import PrincipalOut

router = APIRouter(tags=["identity"])


def _out(principal, development: bool) -> PrincipalOut:  # noqa: ANN001
    return PrincipalOut(
        subject=principal.subject,
        company_code=principal.company_code,
        location_code=principal.location_code,
        category_code=principal.category_code,
        is_development_login=development,
    )


@router.get("/me", response_model=PrincipalOut)
def me(principal: CurrentPrincipal, request: Request) -> PrincipalOut:
    return _out(principal, request.app.state.settings.auth_mode == "dev")


@router.get("/dev/users", response_model=list[PrincipalOut])
def dev_users(request: Request) -> list[PrincipalOut]:
    """The fictional test users for the development login picker. Exists only in dev mode."""
    if request.app.state.settings.auth_mode != "dev":  # pragma: no cover - only mode for now
        raise AppError("Not found.", code="not_found", status_code=404)
    return [_out(p, True) for p in DEV_USERS.values()]
