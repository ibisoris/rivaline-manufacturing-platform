from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api.routers.forecasting import router as forecast_router
from api.routers.health import router
from api.routers.operations import router as operational_router
from api.routers.planning import router as planning_router
from api.routers.production import router as production_router
from database.config import get_settings
from database.session import get_engine
from planning.inventory import PlanningError


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    if get_engine.cache_info().currsize:
        get_engine().dispose()
        get_engine.cache_clear()


def create_app() -> FastAPI:
    application = FastAPI(
        title=get_settings().app_name,
        version="0.6.0",
        lifespan=lifespan,
        description="Read-only local portfolio API for a fictional coatings manufacturer. "
        "All organisations, products, formulations and records are synthetic. "
        "Version 1 operational resources use stable integer IDs, bounded pagination "
        "and Decimal strings. Authentication is not implemented.",
        openapi_tags=[
            {"name": "Operations", "description": "Trusted integrated records and audit summaries"},
            {"name": "Traceability", "description": "Customer-to-supplier and dispatch lineage"},
            {"name": "Analytics", "description": "Shared reporting-view KPI definitions"},
        ],
    )

    @application.exception_handler(PlanningError)
    async def planning_conflict(request: Request, error: PlanningError):
        return JSONResponse(status_code=409, content={"detail": str(error)})

    application.include_router(router)
    application.include_router(production_router)
    application.include_router(forecast_router)
    application.include_router(planning_router)
    application.include_router(operational_router)
    return application


app = create_app()
