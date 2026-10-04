from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    application: str
    environment: str
    status: Literal["ok", "degraded"]
    database: Literal["up", "down", "unconfigured"]
