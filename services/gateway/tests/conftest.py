"""Pytest configuration: default test env before app import."""
from __future__ import annotations

import os

os.environ.setdefault("HAMMRLY_JWT_DEV_HMAC_SECRET", "gateway-unit-test-hmac-secret-at-least-32b")
os.environ.setdefault("HAMMRLY_REDIS_FAKE", "true")
