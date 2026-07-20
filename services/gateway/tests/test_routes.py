from __future__ import annotations

import json
import uuid

from starlette.testclient import TestClient

from hammrly_gateway.app import app
from tests.helpers import campaign_submit_body, desktop_workload, headless_workload, hs256_token


def test_create_job_202_publishes_to_stream_and_index() -> None:
    token = hs256_token()
    with TestClient(app) as client:
        r = client.post(
            "/v2/session",
            json={"workload": desktop_workload()},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 202, r.text
        data = r.json()
        assert data["status"] == "PENDING"
        assert "job_id" in data and "submission_id" in data
        assert data["status_url"] == f"/v1/jobs/{data['job_id']}"
        idx_key = app.state.settings.job_index_redis_prefix + data["job_id"]
        assert app.state.redis.get(idx_key) is not None
        entries = app.state.redis.xrange(app.state.settings.redis_stream_key, count=10)
        assert entries, "expected stream entry"
        _msg_id, fields = entries[-1]
        payload = fields[b"payload"]
        env = json.loads(payload.decode("utf-8"))
        assert env["job_id"] == data["job_id"]
        assert env["submission_id"] == data["submission_id"]
        assert env["tenant_id"] == "tenant-z"


def test_unauthenticated_401() -> None:
    with TestClient(app) as client:
        r = client.post("/v2/session", json={"workload": desktop_workload()})
    assert r.status_code == 401
    assert r.json()["error"] == "unauthenticated"


def test_forbidden_without_scope() -> None:
    token = hs256_token(scope=None)
    with TestClient(app) as client:
        r = client.post(
            "/v2/session",
            json={"workload": desktop_workload()},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 403
    assert r.json()["error"] == "forbidden"


def test_invalid_submission_400() -> None:
    token = hs256_token()
    bad = desktop_workload()
    bad["needs_ingress"] = True
    bad["needs_service"] = False
    with TestClient(app) as client:
        r = client.post(
            "/v2/session",
            json={"workload": bad},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_submission"


def test_ephemeral_storage_request_is_capped() -> None:
    token = hs256_token()
    bad = campaign_submit_body()["template"]
    bad = {**bad, "resources": {**bad["resources"], "ephemeral_storage": "30"}}
    with TestClient(app) as client:
        app.state.settings.ephemeral_storage_max = "25"
        r = client.post(
            "/v2/campaigns",
            json={
                "schema_version": "1.0",
                "campaign": {"name": "c"},
                "template": bad,
                "items": [{"item_key": "a", "input_uri": "https://x"}],
            },
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_campaign"


def test_ephemeral_storage_request_rejects_non_gb_units() -> None:
    token = hs256_token()
    bad = desktop_workload()
    bad["resources"]["ephemeral_storage"] = "30Gi"
    with TestClient(app) as client:
        r = client.post(
            "/v2/session",
            json={"workload": bad},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_submission"


def test_ephemeral_storage_request_can_use_deployer_max() -> None:
    token = hs256_token()
    w = desktop_workload()
    w["resources"]["ephemeral_storage"] = "30"
    with TestClient(app) as client:
        app.state.settings.ephemeral_storage_max = "40"
        r = client.post(
            "/v2/session",
            json={"workload": w},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 202, r.text
        entries = app.state.redis.xrange(app.state.settings.redis_stream_key, count=10)
        _msg_id, fields = entries[-1]
        env = json.loads(fields[b"payload"].decode("utf-8"))
        assert env["workload"]["resources"]["ephemeral_storage"] == "30G"


def test_well_known_openapi() -> None:
    with TestClient(app) as client:
        r = client.get("/.well-known/openapi.json")
    assert r.status_code == 200
    doc = r.json()
    assert "openapi" in doc
    paths = doc.get("paths", {})
    assert "/v2/session" in paths
    assert "/v2/campaigns" in paths


def test_idempotency_replay_same_body() -> None:
    token = hs256_token()
    key = str(uuid.uuid4())
    with TestClient(app) as client:
        r1 = client.post(
            "/v2/session",
            json={"workload": desktop_workload()},
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": key},
        )
        r2 = client.post(
            "/v2/session",
            json={"workload": desktop_workload()},
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": key},
        )
        assert r1.status_code == 202 and r2.status_code == 202
        assert r1.json() == r2.json()
        n = app.state.redis.xlen(app.state.settings.redis_stream_key)
        assert n == 1


def test_idempotency_conflict_409() -> None:
    token = hs256_token()
    key = str(uuid.uuid4())
    with TestClient(app) as client:
        r1 = client.post(
            "/v2/session",
            json={"workload": desktop_workload()},
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": key},
        )
        w2 = desktop_workload()
        w2["name"] = "other-name"
        r2 = client.post(
            "/v2/session",
            json={"workload": w2},
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": key},
        )
    assert r1.status_code == 202
    assert r2.status_code == 409
    assert r2.json()["error"] == "idempotency_conflict"


def test_headless_campaign_networking_normalized() -> None:
    token = hs256_token()
    with TestClient(app) as client:
        r = client.post(
            "/v2/campaigns",
            json=campaign_submit_body(),
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 202, r.text
        stream = app.state.settings.campaign_stream_key
        entries = app.state.redis.xrange(stream, count=10)
        _msg_id, fields = entries[-1]
        env = json.loads(fields[b"payload"].decode("utf-8"))
        assert env["template"]["needs_service"] is False
        assert env["template"]["needs_ingress"] is False


def test_desktop_omitted_networking_normalized_and_idempotent_hash() -> None:
    token = hs256_token()
    key = str(uuid.uuid4())
    with TestClient(app) as client:
        r1 = client.post(
            "/v2/session",
            json={"workload": desktop_workload(with_networking_keys=False)},
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": key},
        )
        r2 = client.post(
            "/v2/session",
            json={"workload": desktop_workload(with_networking_keys=True)},
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": key},
        )
    assert r1.status_code == 202 and r2.status_code == 202
    assert r1.json() == r2.json()


def test_session_status_url_points_at_query_job() -> None:
    token = hs256_token()
    sub = str(uuid.uuid4())
    with TestClient(app) as client:
        app.state.settings.query_public_base_url = "https://query.test"
        r = client.post(
            "/v2/session",
            json={"workload": desktop_workload(with_networking_keys=False)},
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": sub},
        )
        assert r.status_code == 202, r.text
        data = r.json()
        assert data["status_url"] == f"https://query.test/v1/jobs/{data['job_id']}"


def test_session_status_url_path_only_when_query_base_unset() -> None:
    token = hs256_token()
    with TestClient(app) as client:
        app.state.settings.query_public_base_url = None
        r = client.post(
            "/v2/session",
            json={"workload": desktop_workload()},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 202, r.text
        data = r.json()
        assert data["status_url"] == f"/v1/jobs/{data['job_id']}"


def test_healthz() -> None:
    with TestClient(app) as client:
        r = client.get("/healthz")
    assert r.status_code == 200
