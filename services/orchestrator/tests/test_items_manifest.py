from hammrly_orchestrator.campaign.items_manifest import (
    build_items_manifest_document,
    serialize_items_manifest,
)


def test_items_manifest_order_and_workload_merge() -> None:
    campaign_envelope = {
        "campaign_id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
        "tenant_id": "t",
        "user_id": "u",
        "requested_at": "2026-01-01T00:00:00Z",
        "campaign": {"name": "c", "output_uri": "https://out/{item_key}/"},
        "template": {
            "kind": "headless",
            "name": "batch",
            "image": "img:1",
            "resources": {"cpu": "1"},
            "kind_options": {"batch": {"command": ["run"]}},
        },
    }
    entries = [
        {
            "completion_index": 0,
            "item": {"item_key": "a", "input_uri": "https://in/a.fits"},
            "submission_id": "s0",
            "job_id": "j0",
        },
        {
            "completion_index": 1,
            "item": {"item_key": "b", "input_uri": "https://in/b.fits", "batch_args": ["--x"]},
            "submission_id": "s1",
            "job_id": "j1",
        },
    ]
    doc = build_items_manifest_document(campaign_envelope, entries)
    assert doc["items"][0]["workload"]["input_uri"] == "https://in/a.fits"
    assert doc["items"][1]["workload"]["kind_options"]["batch"]["args"] == ["--x"]
    raw = serialize_items_manifest(doc)
    assert b'"completion_index":0' in raw
    assert raw.index(b'"item_key":"a"') < raw.index(b'"item_key":"b"')
