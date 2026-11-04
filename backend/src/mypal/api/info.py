from fastapi import APIRouter

from mypal.api.dependencies import SettingsDep
from mypal.schemas.info import InfoResponse

router = APIRouter(tags=["info"])


@router.get("/info", response_model=InfoResponse)
async def info(settings: SettingsDep) -> InfoResponse:
    """Public facts the interface shows on every screen. No login needed: nothing here is
    specific to a user."""
    return InfoResponse(app=settings.app_name, data_notice=settings.data_notice)
