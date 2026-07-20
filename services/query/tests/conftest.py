"""Pytest env before importing hammrly_query.app."""
from __future__ import annotations

import os

os.environ.setdefault("HAMMRLY_SKIP_DB_BOOTSTRAP", "true")
os.environ.setdefault("HAMMRLY_JWT_DEV_HMAC_SECRET", "query-unit-test-hmac-secret-at-least-32b")
