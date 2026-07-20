from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

from hammrly_catalog.config import Settings


class TapError(RuntimeError):
    pass


def normalize_terms(
    terms: list[str],
    *,
    max_terms: int,
    max_term_length: int,
) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in terms:
        term = str(raw).strip()
        if not term:
            continue
        if len(term) > max_term_length:
            raise ValueError(f"term exceeds maximum length {max_term_length}")
        key = term.casefold()
        if key not in seen:
            out.append(term)
            seen.add(key)
    if not out:
        raise ValueError("at least one term is required")
    if len(out) > max_terms:
        raise ValueError(f"at most {max_terms} terms are allowed")
    return out


def _escape_like_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_").replace("'", "''")


def build_software_search_adql(
    settings: Settings,
    *,
    terms: list[str],
    limit: int,
    offset: int = 0,
) -> str:
    fetch_limit = limit + offset
    if not settings.tap_result_columns:
        raise ValueError("at least one HAMMRLY_TAP_COLUMN_* variable is required")
    if not settings.tap_search_columns_list:
        raise ValueError("HAMMRLY_TAP_SEARCH_COLUMNS must include at least one column")
    columns = ", ".join(dict.fromkeys(settings.tap_result_columns))
    predicates: list[str] = []
    for term in terms:
        pattern = f"%{_escape_like_literal(term).lower()}%"
        per_term = [
            f"LOWER({column}) LIKE '{pattern}' ESCAPE '\\\\'"
            for column in settings.tap_search_columns_list
        ]
        predicates.append("(" + " OR ".join(per_term) + ")")
    where = " AND ".join(predicates)
    return f"SELECT TOP {fetch_limit} {columns} FROM {settings.tap_table} WHERE {where}"


def build_full_table_adql(settings: Settings, *, max_rows: int) -> str:
    if not settings.tap_result_columns:
        raise ValueError("at least one HAMMRLY_TAP_COLUMN_* variable is required")
    columns = ", ".join(dict.fromkeys(settings.tap_result_columns))
    return f"SELECT TOP {max_rows} {columns} FROM {settings.tap_table}"


def _row_value(row: dict[str, Any], column: str) -> Any:
    if column in row:
        return row[column]
    column_lower = column.lower()
    for key, value in row.items():
        if str(key).lower() == column_lower:
            return value
    return None


def _term_matches_row(row: dict[str, Any], settings: Settings, term: str) -> bool:
    needle = term.casefold()
    for column in settings.tap_search_columns_list:
        value = _row_value(row, column)
        if value is None:
            continue
        if needle in str(value).casefold():
            return True
    return False


def filter_software_rows(
    rows: list[dict[str, Any]],
    settings: Settings,
    *,
    terms: list[str],
) -> list[dict[str, Any]]:
    if not terms:
        return list(rows)
    return [row for row in rows if all(_term_matches_row(row, settings, term) for term in terms)]


class TapClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def query(self, adql: str) -> list[dict[str, Any]]:
        sync_url = self._settings.tap_sync_url
        if not sync_url:
            raise TapError("HAMMRLY_TAP_SYNC_URL is not configured")

        data = urllib.parse.urlencode(
            {
                "REQUEST": "doQuery",
                "LANG": "ADQL",
                "FORMAT": self._settings.tap_response_format,
                "QUERY": adql,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            sync_url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._settings.tap_timeout_seconds) as response:
                body = response.read()
        except OSError as e:
            raise TapError(f"TAP query failed: {e}") from e

        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as e:
            raise TapError("TAP response was not JSON") from e
        return parse_tap_json(payload)


def parse_tap_json(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        if all(isinstance(item, dict) for item in payload):
            return [dict(item) for item in payload]
        raise TapError("Unsupported TAP JSON array shape")

    if not isinstance(payload, dict):
        raise TapError("Unsupported TAP JSON response shape")

    rows = payload.get("rows")
    if isinstance(rows, list) and all(isinstance(item, dict) for item in rows):
        return [dict(item) for item in rows]

    data = payload.get("data")
    metadata = payload.get("metadata") or payload.get("fields")
    if isinstance(data, list) and isinstance(metadata, list):
        names: list[str] = []
        for item in metadata:
            if isinstance(item, dict):
                name = item.get("name") or item.get("ID") or item.get("id")
                if name:
                    names.append(str(name))
        if names:
            out: list[dict[str, Any]] = []
            for row in data:
                if isinstance(row, dict):
                    out.append(dict(row))
                elif isinstance(row, list):
                    out.append({name: row[i] if i < len(row) else None for i, name in enumerate(names)})
                else:
                    raise TapError("Unsupported TAP JSON data row shape")
            return out

    raise TapError("Unsupported TAP JSON response shape")
