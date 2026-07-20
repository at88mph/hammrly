"""Pytest env before importing hammrly_catalog.app."""
from __future__ import annotations

import os

os.environ.setdefault("HAMMRLY_JWT_DEV_HMAC_SECRET", "catalog-unit-test-hmac-secret-at-least-32b")
os.environ.setdefault("HAMMRLY_TAP_SYNC_URL", "https://tap.example.test/sync")
os.environ.setdefault("HAMMRLY_TAP_SEARCH_COLUMNS", "uri,description,tools_included,status,supported_modes")
os.environ.setdefault("HAMMRLY_TAP_COLUMN_URI", "uri")
os.environ.setdefault("HAMMRLY_TAP_COLUMN_DESCRIPTION", "description")
os.environ.setdefault("HAMMRLY_TAP_COLUMN_STATUS", "status")
os.environ.setdefault("HAMMRLY_TAP_COLUMN_TOOLS_INCLUDED", "tools_included")
os.environ.setdefault("HAMMRLY_TAP_COLUMN_SUPPORTED_MODES", "supported_modes")
os.environ.setdefault("HAMMRLY_TAP_COLUMN_CPU_ARCHITECTURE", "cpu_architecture")
os.environ.setdefault("HAMMRLY_TAP_COLUMN_MIN_MEMORY", "min_memory")
os.environ.setdefault("HAMMRLY_TAP_COLUMN_RECOMMENDED_MEMORY", "recommended_memory")
os.environ.setdefault("HAMMRLY_TAP_COLUMN_REQUIRES_GPU", "requires_gpu")
os.environ.setdefault("HAMMRLY_TAP_CACHE_TTL_SECONDS", "0")
