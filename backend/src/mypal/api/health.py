from importlib.metadata import version

from fastapi import APIRouter

from mypal.api.dependencies import SettingsDep
from mypal.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(settings: SettingsDep) -> HealthResponse:
    """Liveness check: the process is up and serving requests.

    It does not check Postgres or Qdrant yet; a readiness check is added once they exist (Phase 2).
    """
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        version=version("mypal"),
        environment=settings.environment,
    )
