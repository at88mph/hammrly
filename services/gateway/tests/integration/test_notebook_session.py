"""Live-stack integration: notebook session submit, poll, and access URL."""
from __future__ import annotations

import logging
import pytest

from tests.integration.support import (
    assert_access_url_reachable,
    integration_token,
    poll_job_until_ready,
    submit_notebook_session,
)

logger = logging.getLogger(__name__)
pytestmark = pytest.mark.integration


def test_notebook_session_ready_and_access_url(
    integration_client,
    integration_settings,
) -> None:
    """Create a notebook session, poll Query until ready, then GET access_url."""
    token = integration_token(integration_settings)
    created = submit_notebook_session(integration_client, integration_settings, token)
    job_id = created["job_id"]
    logger.info("job_id: %s", job_id)

    detail = poll_job_until_ready(
        integration_client,
        integration_settings,
        job_id,
        token,
    )
    assert detail["status"] == "ready"
    access_url = detail.get("access_url")
    assert access_url, f"expected access_url on ready job; got {detail!r}"

    event_types = {e.get("event_type") for e in detail.get("events") or []}
    assert "session_ready" in event_types

    assert_access_url_reachable(integration_client, access_url)
