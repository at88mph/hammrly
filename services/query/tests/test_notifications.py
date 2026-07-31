from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from starlette.testclient import TestClient

from hammrly_query.app import app, get_db, get_rw_db
from tests.helpers import hs256_token


def _sample_notification(**overrides):
    now = datetime(2026, 7, 31, 12, 0, 0, tzinfo=timezone.utc)
    base = dict(
        id=7,
        kind="campaign_terminal",
        subject="Campaign demo: partial_failed",
        body_json={
            "campaign_id": "aa0e8400-e29b-41d4-a716-446655440099",
            "fail_count": 2,
            "portal_path": "/campaigns/aa0e8400-e29b-41d4-a716-446655440099",
        },
        resource_type="campaign",
        resource_id="aa0e8400-e29b-41d4-a716-446655440099",
        created_at=now,
        read_at=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_list_notifications() -> None:
    note = _sample_notification()

    def _override():
        s = MagicMock()
        s.scalars.return_value.all.return_value = [note]
        yield s

    app.dependency_overrides[get_db] = _override
    try:
        with TestClient(app) as client:
            r = client.get(
                "/v1/me/notifications",
                headers={"Authorization": f"Bearer {hs256_token()}"},
            )
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body["items"]) == 1
        assert body["items"][0]["id"] == 7
        assert body["items"][0]["kind"] == "campaign_terminal"
    finally:
        app.dependency_overrides.clear()


def test_unread_count() -> None:
    def _override():
        s = MagicMock()
        s.scalar.return_value = 3
        yield s

    app.dependency_overrides[get_db] = _override
    try:
        with TestClient(app) as client:
            r = client.get(
                "/v1/me/notifications/unread_count",
                headers={"Authorization": f"Bearer {hs256_token()}"},
            )
        assert r.status_code == 200
        assert r.json()["unread_count"] == 3
    finally:
        app.dependency_overrides.clear()


def test_mark_read() -> None:
    note = _sample_notification()

    def _rw():
        s = MagicMock()
        s.scalar.return_value = note
        yield s

    app.dependency_overrides[get_rw_db] = _rw
    try:
        with TestClient(app) as client:
            r = client.post(
                "/v1/me/notifications/7/read",
                headers={"Authorization": f"Bearer {hs256_token()}"},
            )
        assert r.status_code == 200, r.text
        assert r.json()["id"] == 7
        assert note.read_at is not None
    finally:
        app.dependency_overrides.clear()
