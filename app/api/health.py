"""Liveness endpoint.

Reports data-residency posture alongside liveness so that a misconfigured
region is visible from a probe rather than discovered during an audit.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app import __version__
from app.config import Settings, get_settings

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
    environment: str
    region: str
    region_is_eea: bool


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings: Settings = get_settings()
    return HealthResponse(
        version=__version__,
        environment=settings.app_env,
        region=settings.deployment_region,
        region_is_eea=settings.region_is_eea,
    )
