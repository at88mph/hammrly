from __future__ import annotations

import json
from unittest.mock import MagicMock

import fakeredis
from starlette.testclient import TestClient

from hammrly_query.app import app, get_db
from hammrly_query.config import Settings
from hammrly_query.job_index import index_key
from tests.helpers import hs256_token


def _put_index(settings: Settings, r, envelope: dict, *, status: str = "pending") -> None:
    record = {
        "schema_version": "1.0",
        "job_id": envelope["job_id"],
        "submission_id": envelope["submission_id"],
        "tenant_id": envelope["tenant_id"],
        "user_id": envelope["user_id"],
        "status": status,
        "requested_at": envelope["requested_at"],
        "queue_name": "default",
        "payload_summary": {
            "kind": envelope["workload"]["kind"],
            "name": envelope["workload"]["name"],
            "image": envelope["workload"]["image"],
            "gpu_count": envelope["workload"].get("gpu_count", 0),
            "needs_ingress": envelope["workload"].get("needs_ingress"),
        },
    }
    r.set(index_key(settings, envelope["job_id"]), json.dumps(record, separators=(",", ":")))


def _sample_envelope() -> dict:
    return {
        "job_id": "550e8400-e29b-41d4-a716-446655440000",
        "submission_id": "660e8400-e29b-41d4-a716-446655440001",
        "tenant_id": "tenant-z",
        "user_id": "user-1",
        "requested_at": "2026-01-15T12:00:00Z",
        "workload": {
            "kind": "desktop",
            "name": "sess",
            "image": "img:latest",
            "gpu_count": 0,
            "needs_ingress": True,
        },
    }


def test_get_job_from_redis_index_when_postgres_misses() -> None:
    settings = Settings()

    def _override():
        s = MagicMock()
        s.scalar.return_value = None
        yield s

    app.dependency_overrides[get_db] = _override
    r = fakeredis.FakeRedis(decode_responses=False)
    _put_index(settings, r, _sample_envelope(), status="pending")
    try:
        token = hs256_token()
        with TestClient(app) as client:
            app.state.redis = r
            resp = client.get(
                "/v1/jobs/550e8400-e29b-41d4-a716-446655440000",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "pending"
        assert body["events"] == []
        assert body["payload_summary"]["kind"] == "desktop"
    finally:
        app.dependency_overrides.clear()
        app.state.redis = None


def test_get_job_redis_index_wrong_user_404() -> None:
    settings = Settings()

    def _override():
        s = MagicMock()
        s.scalar.return_value = None
        yield s

    app.dependency_overrides[get_db] = _override
    r = fakeredis.FakeRedis(decode_responses=False)
    env = _sample_envelope()
    env["user_id"] = "other-user"
    _put_index(settings, r, env)
    try:
        token = hs256_token()
        with TestClient(app) as client:
            app.state.redis = r
            resp = client.get(
                "/v1/jobs/550e8400-e29b-41d4-a716-446655440000",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()
        app.state.redis = None


def test_get_job_redis_received_when_postgres_misses() -> None:
    settings = Settings()

    def _override():
        s = MagicMock()
        s.scalar.return_value = None
        yield s

    app.dependency_overrides[get_db] = _override
    r = fakeredis.FakeRedis(decode_responses=False)
    _put_index(settings, r, _sample_envelope(), status="received")
    try:
        token = hs256_token()
        with TestClient(app) as client:
            app.state.redis = r
            resp = client.get(
                "/v1/jobs/550e8400-e29b-41d4-a716-446655440000",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "received"
    finally:
        app.dependency_overrides.clear()
        app.state.redis = None
