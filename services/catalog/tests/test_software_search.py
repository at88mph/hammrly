from __future__ import annotations

from hammrly_catalog.config import Settings
from hammrly_catalog.software_search import SoftwareSearchService
from hammrly_catalog.tap import TapClient, build_full_table_adql


class RecordingTapClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def query(self, adql: str) -> list[dict[str, str]]:
        self.calls.append(adql)
        return [
            {"uri": "ska:gpu-radio:1.0.0", "description": "Both terms"},
            {"uri": "ska:gpu-only:1.0.0", "description": "GPU only"},
        ]


def test_search_uses_cache_without_requerying_tap() -> None:
    settings = Settings(tap_cache_ttl_seconds=60, tap_cache_max_rows=100)
    tap_client = RecordingTapClient()
    service = SoftwareSearchService(settings, tap_client)

    first = service.search(terms=["gpu"], limit=10, offset=0)
    second = service.search(terms=["radio"], limit=10, offset=0)

    assert len(tap_client.calls) == 1
    assert tap_client.calls[0] == build_full_table_adql(settings, max_rows=100)
    assert [row["uri"] for row in first] == ["ska:gpu-radio:1.0.0", "ska:gpu-only:1.0.0"]
    assert [row["uri"] for row in second] == ["ska:gpu-radio:1.0.0"]


def test_search_refreshes_cache_after_ttl(monkeypatch) -> None:
    settings = Settings(tap_cache_ttl_seconds=30, tap_cache_max_rows=100)
    tap_client = RecordingTapClient()
    service = SoftwareSearchService(settings, tap_client)
    now = {"value": 1000.0}

    monkeypatch.setattr("hammrly_catalog.software_search.time.monotonic", lambda: now["value"])

    service.search(terms=["tool"], limit=10, offset=0)
    now["value"] += 10
    service.search(terms=["tool"], limit=10, offset=0)
    now["value"] += 25
    service.search(terms=["tool"], limit=10, offset=0)

    assert len(tap_client.calls) == 2


def test_search_without_cache_queries_tap_directly() -> None:
    settings = Settings(tap_cache_ttl_seconds=0)
    tap_client = RecordingTapClient()
    service = SoftwareSearchService(settings, tap_client)

    service.search(terms=["gpu", "radio"], limit=25, offset=0)

    assert len(tap_client.calls) == 1
    assert " WHERE " in tap_client.calls[0]
    assert "%gpu%" in tap_client.calls[0]
    assert "%radio%" in tap_client.calls[0]
