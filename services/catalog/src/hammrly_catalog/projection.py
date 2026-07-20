from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from hammrly_catalog.config import Settings


class MemorySummary(BaseModel):
    min: Optional[int] = None
    recommended: Optional[int] = None


class SoftwareSearchItem(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    status: Optional[str] = None
    tools_included: list[str] = Field(default_factory=list)
    supported_modes: list[str] = Field(default_factory=list)
    cpu_architecture: list[str] = Field(default_factory=list)
    memory: MemorySummary = Field(default_factory=MemorySummary)
    gpu_required: bool = False


class SoftwareSearchResponse(BaseModel):
    items: list[SoftwareSearchItem]
    limit: int
    offset: int


def project_rows(
    rows: list[dict[str, Any]],
    settings: Settings,
    *,
    limit: int,
    offset: int,
) -> SoftwareSearchResponse:
    sliced = rows[offset : offset + limit]
    return SoftwareSearchResponse(
        items=[project_row(row, settings) for row in sliced],
        limit=limit,
        offset=offset,
    )


def project_row(row: dict[str, Any], settings: Settings) -> SoftwareSearchItem:
    uri = str(_configured_value(row, settings, "uri") or "").strip()
    return SoftwareSearchItem(
        id=uri,
        name=_name_from_uri(uri),
        description=_str_or_none(_configured_value(row, settings, "description")),
        status=_str_or_none(_configured_value(row, settings, "status")),
        tools_included=_string_list(_configured_value(row, settings, "tools_included")),
        supported_modes=_string_list(_configured_value(row, settings, "supported_modes")),
        cpu_architecture=_string_list(_configured_value(row, settings, "cpu_architecture")),
        memory=MemorySummary(
            min=_int_or_none(_configured_value(row, settings, "min_memory")),
            recommended=_int_or_none(_configured_value(row, settings, "recommended_memory")),
        ),
        gpu_required=_bool_value(_configured_value(row, settings, "requires_gpu")),
    )


def _configured_value(row: dict[str, Any], settings: Settings, name: str) -> Any:
    column = settings.tap_column(name)
    if not column:
        return None
    return _value(row, column)


def _value(row: dict[str, Any], key: str) -> Any:
    if key in row:
        return row[key]
    key_lower = key.lower()
    for k, v in row.items():
        if str(k).lower() == key_lower:
            return v
    return None


def _name_from_uri(uri: str) -> str:
    parts = uri.split(":")
    if len(parts) >= 2 and parts[1]:
        return parts[1]
    return uri


def _str_or_none(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        raw = value
    elif isinstance(value, tuple):
        raw = list(value)
    else:
        raw = str(value).replace(";", ",").split(",")

    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        s = str(item).strip()
        if not s:
            continue
        key = s.casefold()
        if key not in seen:
            out.append(s)
            seen.add(key)
    return out


def _int_or_none(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "t", "yes", "y"}
