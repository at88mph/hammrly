from __future__ import annotations

import threading
import time
from typing import Any

from hammrly_catalog.config import Settings
from hammrly_catalog.tap import (
    TapClient,
    build_full_table_adql,
    build_software_search_adql,
    filter_software_rows,
)


class SoftwareSearchService:
    def __init__(self, settings: Settings, tap_client: TapClient) -> None:
        self._settings = settings
        self._tap_client = tap_client
        self._cache_lock = threading.Lock()
        self._cache_rows: list[dict[str, Any]] | None = None
        self._cache_fetched_at: float | None = None

    def search(
        self,
        *,
        terms: list[str],
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        if self._settings.tap_cache_ttl_seconds <= 0:
            adql = build_software_search_adql(
                self._settings,
                terms=terms,
                limit=limit,
                offset=offset,
            )
            return self._tap_client.query(adql)

        rows = self._cached_rows()
        filtered = filter_software_rows(rows, self._settings, terms=terms)
        return filtered[: limit + offset]

    def _cached_rows(self) -> list[dict[str, Any]]:
        ttl = self._settings.tap_cache_ttl_seconds
        now = time.monotonic()
        with self._cache_lock:
            if (
                self._cache_rows is not None
                and self._cache_fetched_at is not None
                and now - self._cache_fetched_at < ttl
            ):
                return self._cache_rows

        adql = build_full_table_adql(
            self._settings,
            max_rows=self._settings.tap_cache_max_rows,
        )
        rows = self._tap_client.query(adql)

        with self._cache_lock:
            self._cache_rows = rows
            self._cache_fetched_at = time.monotonic()
            return rows
