from __future__ import annotations

from typing import Optional

from starlette.testclient import TestClient

from hammrly_catalog.app import app, get_software_search
from tests.helpers import hs256_token


class FakeSoftwareSearch:
    def __init__(self) -> None:
        self.adql: Optional[str] = None

    def search(
        self,
        *,
        terms: list[str],
        limit: int,
        offset: int,
    ) -> list[dict[str, object]]:
        from hammrly_catalog.config import Settings
        from hammrly_catalog.tap import build_software_search_adql

        settings = Settings()
        adql = build_software_search_adql(
            settings,
            terms=terms,
            limit=limit,
            offset=offset,
        )
        self.adql = adql
        return [
            {
                "uri": "ska:dsc-037-delay-ps:0.1.3",
                "description": "Delay processing",
                "status": "STABLE",
                "tools_included": "python,casacore",
                "supported_modes": "NOTEBOOK,HEADLESS",
                "cpu_architecture": "amd64",
                "min_memory": 8,
                "recommended_memory": 16,
                "requires_gpu": True,
            }
        ]


def test_post_software_query_ands_terms_and_returns_projection() -> None:
    fake = FakeSoftwareSearch()

    def override_search() -> FakeSoftwareSearch:
        return fake

    app.dependency_overrides[get_software_search] = override_search
    try:
        token = hs256_token()
        with TestClient(app) as client:
            r = client.post(
                "/v1/software/query?limit=25",
                content="term=gpu&term=radio",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
        assert r.status_code == 200, r.text
        assert fake.adql is not None
        assert "%gpu%" in fake.adql
        assert "%radio%" in fake.adql
        assert ") AND (" in fake.adql
        body = r.json()
        assert body["limit"] == 25
        item = body["items"][0]
        assert item["id"] == "ska:dsc-037-delay-ps:0.1.3"
        assert item["name"] == "dsc-037-delay-ps"
        assert item["description"] == "Delay processing"
        assert item["status"] == "STABLE"
        assert item["tools_included"] == ["python", "casacore"]
        assert item["supported_modes"] == ["NOTEBOOK", "HEADLESS"]
        assert item["cpu_architecture"] == ["amd64"]
        assert item["memory"] == {"min": 8, "recommended": 16}
        assert item["gpu_required"] is True
    finally:
        app.dependency_overrides.clear()


def test_post_software_query_requires_terms() -> None:
    token = hs256_token()
    with TestClient(app) as client:
        r = client.post(
            "/v1/software/query",
            content="",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_search"


def test_post_software_query_requires_auth() -> None:
    with TestClient(app) as client:
        r = client.post("/v1/software/query", data={"term": "gpu"})
    assert r.status_code == 401


def test_well_known_openapi() -> None:
    with TestClient(app) as client:
        r = client.get("/.well-known/openapi.json")
    assert r.status_code == 200
    assert "/v1/software/query" in r.json().get("paths", {})
