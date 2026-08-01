from __future__ import annotations

from unittest.mock import MagicMock

from starlette.testclient import TestClient

from hammrly_query.app import app, get_db
from tests.helpers import hs256_token, sample_event, sample_submission_row


def _mock_db_with_submission(sub=None, events=None):
    sub = sub or sample_submission_row()
    events = events or [sample_event()]

    def _override():
        s = MagicMock()

        def scalars_impl(*_a, **_k):
            m = MagicMock()
            m.all.return_value = events
            return m

        s.scalar.return_value = sub
        s.scalars.side_effect = scalars_impl
        yield s

    return _override


def test_get_job_200() -> None:
    app.dependency_overrides[get_db] = _mock_db_with_submission()
    try:
        token = hs256_token()
        with TestClient(app) as client:
            r = client.get(
                "/v1/jobs/550e8400-e29b-41d4-a716-446655440000",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["job_id"] == "550e8400-e29b-41d4-a716-446655440000"
        assert body["submission_id"] == "660e8400-e29b-41d4-a716-446655440001"
        assert body["payload_summary"]["kind"] == "desktop"
        assert body["access_url"] == "https://sessions.example/hammrly/sessions/x/"
        assert body["payload_summary"]["gpu_count"] == 0
        assert len(body["events"]) == 1
        assert body["events"][0]["event_type"] == "queued"
    finally:
        app.dependency_overrides.clear()


def test_get_job_404() -> None:
    def _override():
        s = MagicMock()
        s.scalar.return_value = None
        yield s

    app.dependency_overrides[get_db] = _override
    try:
        token = hs256_token()
        with TestClient(app) as client:
            r = client.get(
                "/v1/jobs/550e8400-e29b-41d4-a716-446655440000",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert r.status_code == 404
        assert r.json()["error"] == "not_found"
    finally:
        app.dependency_overrides.clear()


def test_list_interactive_jobs() -> None:
    sub = sample_submission_row()

    def _override():
        s = MagicMock()
        s.scalars.return_value.all.return_value = [sub]
        yield s

    app.dependency_overrides[get_db] = _override
    try:
        token = hs256_token()
        with TestClient(app) as client:
            r = client.get(
                "/v1/me/jobs/interactive",
                headers={"Authorization": f"Bearer {token}"},
            )
            filtered = client.get(
                "/v1/me/jobs/interactive",
                params=[("status", "ready"), ("status", "running")],
                headers={"Authorization": f"Bearer {token}"},
            )
        assert r.status_code == 200, r.text
        data = r.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["kind"] == "desktop"
        assert data["items"][0]["access_url"] == "https://sessions.example/hammrly/sessions/x/"
        assert filtered.status_code == 200, filtered.text
        assert len(filtered.json()["items"]) == 1
    finally:
        app.dependency_overrides.clear()


def test_unauthenticated_401() -> None:
    with TestClient(app) as client:
        r = client.get("/v1/me/jobs/interactive")
    assert r.status_code == 401


def test_well_known_openapi() -> None:
    with TestClient(app) as client:
        r = client.get("/.well-known/openapi.json")
    assert r.status_code == 200
    doc = r.json()
    assert "/v1/jobs/{job_id}" in doc.get("paths", {})
    assert "/v1/me/jobs/interactive" in doc.get("paths", {})
