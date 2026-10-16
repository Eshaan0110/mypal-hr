from typing import Literal

from pydantic import BaseModel

from mypal.config import Environment


class HealthResponse(BaseModel):
    status: Literal["ok"]
    app: str
    version: str
    environment: Environment


class ReadinessResponse(BaseModel):
    status: Literal["ready"]
    database: Literal["ok"]
