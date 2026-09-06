"""Application settings.

Region is a first-class setting rather than deployment trivia: invariant I5
(no raw PII crosses the EEA boundary) is meaningless if the application itself
is running outside the EEA. ``Settings`` therefore refuses to start a non-local
environment in a non-EU region, so a misconfigured deploy fails loudly at boot
instead of quietly processing European personal data in Ohio.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "ci", "staging", "production"]

# Regions that sit inside the EEA. Extend deliberately, never casually.
EU_REGION_PREFIXES: tuple[str, ...] = ("eu-", "europe-", "eu_")


class Settings(BaseSettings):
    """Runtime configuration, loaded from environment or a local .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Environment = "local"
    log_level: str = "INFO"

    # --- data residency (invariant I5) ---
    deployment_region: str = Field(
        default="eu-central-1",
        description="Region the application runs in. Must be EEA outside local/ci.",
    )

    # --- infrastructure ---
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/usa"
    redis_url: str = "redis://localhost:6379/0"

    # --- models (see CLAUDE.md "Claude API rules") ---
    model_main: str = "claude-opus-5"
    model_support: str = "claude-sonnet-5"
    model_cheap: str = "claude-haiku-4-5"

    @property
    def region_is_eea(self) -> bool:
        return self.deployment_region.lower().startswith(EU_REGION_PREFIXES)

    @model_validator(mode="after")
    def _enforce_eu_residency(self) -> Settings:
        """Fail closed: a deployed environment must run inside the EEA."""
        if self.app_env in ("staging", "production") and not self.region_is_eea:
            raise ValueError(
                f"deployment_region={self.deployment_region!r} is outside the EEA. "
                f"Invariant I5 requires {self.app_env} to run in an EU region."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor. Call ``get_settings.cache_clear()`` in tests."""
    return Settings()
