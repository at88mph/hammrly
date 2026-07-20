from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt


def hs256_token(
    *,
    secret: str = "catalog-unit-test-hmac-secret-at-least-32b",
    sub: str = "user-123",
    tenant: str = "tenant-a",
    scope: str = "hammrly:catalog:read",
) -> str:
    now = datetime.now(timezone.utc)
    claims: dict[str, Any] = {
        "sub": sub,
        "hammrly_tenant_id": tenant,
        "scope": scope,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=15)).timestamp()),
    }
    return jwt.encode(claims, secret, algorithm="HS256")
