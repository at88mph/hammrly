from __future__ import annotations

import json
import uuid

from starlette.testclient import TestClient

from hammrly_gateway.app import app
from tests.helpers import campaign_submit_body, desktop_workload, headless_workload, hs256_token


def test_create_campaign_202_publishes_to_campaign_stream() -> None:
    token = hs256_token()
    with TestClient(app) as client:
        r = client.post(
            "/v2/campaigns",
            json=campaign_submit_body(),
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 202, r.text
        data = r.json()
        assert data["status"] == "accepted"
        assert data["item_count"] == 1
        assert "/v1/me/campaigns/" in data["status_url"]
        stream = app.state.settings.campaign_stream_key
        entries = app.state.redis.xrange(stream, count=10)
        assert entries
        _msg_id, fields = entries[-1]
        env = json.loads(fields[b"payload"].decode("utf-8"))
        assert env["campaign_id"] == data["campaign_id"]
        assert env["template"]["kind"] == "headless"


def test_headless_session_rejected_use_campaign() -> None:
    token = hs256_token()
    with TestClient(app) as client:
        r = client.post(
            "/v2/session",
            json={"workload": headless_workload()},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 400
    assert r.json()["error"] == "use_campaign_submit"


def test_campaign_idempotency() -> None:
    token = hs256_token()
    key = str(uuid.uuid4())
    body = campaign_submit_body()
    with TestClient(app) as client:
        r1 = client.post(
            "/v2/campaigns",
            json=body,
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": key},
        )
        r2 = client.post(
            "/v2/campaigns",
            json=body,
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": key},
        )
        assert r1.status_code == 202 and r2.status_code == 202
        assert r1.json()["campaign_id"] == r2.json()["campaign_id"]
        stream = app.state.settings.campaign_stream_key
        assert app.state.redis.xlen(stream) == 1


def test_desktop_session_still_works() -> None:
    token = hs256_token()
    with TestClient(app) as client:
        r = client.post(
            "/v2/session",
            json={"workload": desktop_workload(with_networking_keys=False)},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 202, r.text
