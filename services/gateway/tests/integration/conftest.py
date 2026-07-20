"""Fixtures for live-stack integration tests."""
from __future__ import annotations

import os

import httpx
import pytest

from tests.integration.support import IntegrationSettings, integration_settings_from_env


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "integration: live Hammrly stack (set HAMMRLY_INTEGRATION=1)",
    )


def _integration_enabled() -> bool:
    return os.environ.get("HAMMRLY_INTEGRATION", "").strip() == "1"


@pytest.fixture(scope="session")
def integration_settings() -> IntegrationSettings:
    if not _integration_enabled():
        pytest.skip(
            "Integration tests are disabled. Set HAMMRLY_INTEGRATION=1 and point "
            "HAMMRLY_GATEWAY_URL / HAMMRLY_QUERY_URL at a running stack with K8s submit enabled."
        )
    return integration_settings_from_env()


@pytest.fixture(scope="session")
def integration_client(integration_settings: IntegrationSettings) -> httpx.Client:
    with httpx.Client(
        timeout=httpx.Timeout(60.0, connect=10.0),
        verify=integration_settings.tls_verify,
        follow_redirects=True,
    ) as client:
        for base, label in (
            (integration_settings.gateway_url, "gateway"),
            (integration_settings.query_url, "query"),
        ):
            r = client.get(f"{base}/healthz")
            if r.status_code != 200:
                pytest.fail(f"{label} healthz at {base}/healthz returned {r.status_code}: {r.text}")
        yield client
