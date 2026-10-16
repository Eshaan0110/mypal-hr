import logging
from importlib.metadata import version

from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from mypal.api.dependencies import SettingsDep
from mypal.db.session import DbSession
from mypal.errors import AppError
from mypal.schemas.errors import ErrorResponse
from mypal.schemas.health import HealthResponse, ReadinessResponse

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/health", response_model=HealthResponse)
def health(settings: SettingsDep) -> HealthResponse:
    """Liveness: the process is up and serving requests. Deliberately checks nothing else, so a
    database outage does not make an orchestrator restart a healthy process."""
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        version=version("mypal"),
        environment=settings.environment,
    )


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ErrorResponse}},
)
def readiness(session: DbSession) -> ReadinessResponse:
    """Readiness: the service can do useful work, i.e. its database answers queries."""
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        # Details go to the log only; the client gets a generic message.
        logger.warning("readiness check failed: database unavailable", exc_info=exc)
        raise AppError(
            "The database is unavailable.", code="database_unavailable", status_code=503
        ) from exc
    return ReadinessResponse(status="ready", database="ok")
