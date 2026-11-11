from hammrly_orchestrator.k8s.jobset_spec import (
    batch_parallelism,
    campaign_template_for_indexed_job,
)


def test_campaign_template_strips_shared_uris() -> None:
    tpl = {
        "kind": "headless",
        "name": "x",
        "image": "i",
        "input_uri": "https://shared",
        "output_uri": "https://out/",
        "kind_options": {"batch": {"parallelism": 4}},
    }
    out = campaign_template_for_indexed_job(tpl)
    assert "input_uri" not in out
    assert "output_uri" not in out
    assert batch_parallelism(tpl, item_count=2) == 2
