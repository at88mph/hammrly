from __future__ import annotations

from hammrly_catalog.config import Settings
from hammrly_catalog.projection import project_row
from hammrly_catalog.tap import (
    build_full_table_adql,
    build_software_search_adql,
    filter_software_rows,
    normalize_terms,
    parse_tap_json,
)


def test_normalize_terms_deduplicates_and_rejects_empty() -> None:
    assert normalize_terms([" gpu ", "GPU", "radio"], max_terms=8, max_term_length=64) == ["gpu", "radio"]


def test_build_software_search_adql_ands_repeated_terms() -> None:
    settings = Settings()
    adql = build_software_search_adql(
        settings,
        terms=["gpu", "radio"],
        limit=50,
        offset=10,
    )
    assert adql.startswith("SELECT TOP 60 ")
    assert " FROM software_discovery WHERE " in adql
    assert "LOWER(uri) LIKE '%gpu%' ESCAPE '\\\\'" in adql
    assert ") AND (" in adql
    assert "LOWER(uri) LIKE '%radio%' ESCAPE '\\\\'" in adql


def test_build_software_search_adql_selects_only_configured_columns() -> None:
    settings = Settings(
        tap_search_columns="ivoid,abstract",
        tap_columns={"uri": "ivoid", "description": "abstract"},
    )
    adql = build_software_search_adql(settings, terms=["gpu"], limit=10)

    assert adql.startswith("SELECT TOP 10 ivoid, abstract FROM software_discovery")
    assert "status" not in adql


def test_build_full_table_adql_selects_only_configured_columns() -> None:
    settings = Settings(
        tap_columns={"uri": "ivoid", "description": "abstract"},
        tap_cache_max_rows=500,
    )
    adql = build_full_table_adql(settings, max_rows=500)

    assert adql == "SELECT TOP 500 ivoid, abstract FROM software_discovery"


def test_filter_software_rows_ands_terms_case_insensitively() -> None:
    settings = Settings()
    rows = [
        {"uri": "ska:gpu-tool:1.0.0", "description": "Radio pipeline"},
        {"uri": "ska:other:1.0.0", "description": "CPU only"},
    ]
    filtered = filter_software_rows(rows, settings, terms=["gpu", "radio"])
    assert filtered == [rows[0]]


def test_parse_tap_json_metadata_data_shape() -> None:
    rows = parse_tap_json(
        {
            "metadata": [{"name": "uri"}, {"name": "description"}],
            "data": [["ska:tool:1.0.0", "desc"]],
        }
    )
    assert rows == [{"uri": "ska:tool:1.0.0", "description": "desc"}]


def test_project_row_compact_software_discovery_fields() -> None:
    settings = Settings()
    item = project_row(
        {
            "uri": "ska:dsc-037-delay-ps:0.1.3",
            "description": "Delay processing",
            "status": "STABLE",
            "tools_included": "python,casacore,python",
            "supported_modes": "NOTEBOOK,HEADLESS",
            "cpu_architecture": "amd64,arm64",
            "min_memory": "8",
            "recommended_memory": 16,
            "requires_gpu": "true",
        },
        settings,
    )
    assert item.id == "ska:dsc-037-delay-ps:0.1.3"
    assert item.name == "dsc-037-delay-ps"
    assert item.description == "Delay processing"
    assert item.status == "STABLE"
    assert item.tools_included == ["python", "casacore"]
    assert item.supported_modes == ["NOTEBOOK", "HEADLESS"]
    assert item.cpu_architecture == ["amd64", "arm64"]
    assert item.memory.min == 8
    assert item.memory.recommended == 16
    assert item.gpu_required is True


def test_project_row_uses_only_configured_column_mappings() -> None:
    settings = Settings(
        tap_columns={
            "uri": "ivoid",
            "description": "abstract",
            "requires_gpu": "gpu_flag",
        },
    )
    item = project_row(
        {
            "ivoid": "ska:dsc-037-delay-ps:0.1.3",
            "abstract": "Delay processing",
            "status": "STABLE",
            "gpu_flag": "true",
        },
        settings,
    )

    assert item.id == "ska:dsc-037-delay-ps:0.1.3"
    assert item.description == "Delay processing"
    assert item.status is None
    assert item.gpu_required is True
