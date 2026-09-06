"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI

from app import __version__
from app.api import health


def create_app() -> FastAPI:
    app = FastAPI(
        title="Universal Sales Agent",
        description="Multi-tenant, EU-compliant agentic support and sales platform.",
        version=__version__,
    )
    app.include_router(health.router)
    return app


app = create_app()
