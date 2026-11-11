from hammrly_orchestrator.k8s.labels import base_labels_for_campaign_jobset, resource_names_from_campaign


def test_resource_names_from_campaign() -> None:
    js, cm, _ = resource_names_from_campaign("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    assert js.startswith("js")
    assert cm.endswith("-items")
    assert len(js) <= 63


def test_base_labels_for_campaign_jobset() -> None:
    labels = base_labels_for_campaign_jobset(
        {
            "campaign_id": "c",
            "tenant_id": "t",
            "user_id": "user-1",
            "template": {"kind": "headless"},
        },
        kueue_queue_name="headless-q",
        user_id_label_value="user-1",
    )
    assert labels["hammrly.io/campaign-jobset"] == "indexed"
    assert labels["kueue.x-k8s.io/queue-name"] == "headless-q"
