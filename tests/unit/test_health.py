"""M0-1 acceptance: /health returns 200, and region config fails closed."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings


def test_health_returns_200(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"]


def test_health_reports_residency_posture(client: TestClient) -> None:
    body = client.get("/health").json()
    assert "region" in body
    assert body["region_is_eea"] is True


@pytest.mark.parametrize("region", ["eu-central-1", "europe-west4", "eu-west-1"])
def test_eu_regions_accepted_in_production(region: str) -> None:
    settings = Settings(app_env="production", deployment_region=region)
    assert settings.region_is_eea is True


@pytest.mark.parametrize("region", ["us-east-1", "ap-south-1", "us-central1"])
def test_non_eu_region_rejected_in_production(region: str) -> None:
    """Invariant I5: a deployed environment outside the EEA must not boot."""
    with pytest.raises(ValueError, match="outside the EEA"):
        Settings(app_env="production", deployment_region=region)


def test_non_eu_region_allowed_locally() -> None:
    """Local development is exempt; the guard targets deployed environments."""
    settings = Settings(app_env="local", deployment_region="us-east-1")
    assert settings.region_is_eea is False
