from fastapi import APIRouter, Depends, Response

from api.schemas.health import HealthResponse
from api.services.health import database_status
from database.config import Settings, get_settings

router = APIRouter()


@router.get("/health", response_model=HealthResponse, responses={503: {"model": HealthResponse}})
def health(
    response: Response,
    database: str = Depends(database_status),
    settings: Settings = Depends(get_settings),
) -> HealthResponse:
    if database != "up":
        response.status_code = 503
    return HealthResponse(
        application=settings.app_name,
        environment=settings.app_env,
        status="ok" if database == "up" else "degraded",
        database=database,
    )
