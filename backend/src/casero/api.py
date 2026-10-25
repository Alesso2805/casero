from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"]


def create_app() -> FastAPI:
    app = FastAPI(
        title="Casero API",
        version="0.1.0",
        openapi_url="/api/openapi.json",
        docs_url=None,
        redoc_url=None,
    )

    @app.get("/api/health")
    def health() -> HealthResponse:
        """Report that the API process is up."""
        return HealthResponse(status="ok")

    return app
