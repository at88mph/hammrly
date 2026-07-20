from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

import jwt
from jwt import PyJWKClient

from hammrly_catalog.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class Principal:
    user_id: str
    raw_claims: dict[str, Any]
    tenant_from_token: Optional[str]


def _parse_scope_claim(claims: dict[str, Any]) -> set[str]:
    raw = claims.get("scope")
    if isinstance(raw, str):
        return {p for p in raw.split() if p}
    if isinstance(raw, list):
        return {str(x) for x in raw if x}
    return set()


def enforce_scopes(claims: dict[str, Any], required: list[str]) -> None:
    if not required:
        return
    present = _parse_scope_claim(claims)
    missing = [s for s in required if s not in present]
    if missing:
        raise PermissionError(f"insufficient_scope: missing {missing}")


def resolve_tenant_claim(claims: dict[str, Any], claim_name: str) -> Optional[str]:
    v = claims.get(claim_name)
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def validate_bearer_token(token: str, settings: Settings) -> Principal:
    if settings.jwt_dev_hmac_secret:
        try:
            payload = jwt.decode(
                token,
                settings.jwt_dev_hmac_secret,
                algorithms=["HS256"],
                issuer=settings.jwt_issuer if settings.jwt_issuer else None,
                audience=settings.jwt_audience if settings.jwt_audience else None,
                leeway=settings.jwt_leeway_seconds,
                options={
                    "verify_aud": bool(settings.jwt_audience),
                    "verify_iss": bool(settings.jwt_issuer),
                },
            )
        except jwt.PyJWTError as e:
            logger.debug("JWT dev decode failed: %s", e)
            raise ValueError("invalid_token") from e
    else:
        if not settings.jwt_jwks_url:
            raise RuntimeError("HAMMRLY_JWT_JWKS_URL or HAMMRLY_JWT_DEV_HMAC_SECRET must be configured")
        jwks = PyJWKClient(settings.jwt_jwks_url)
        try:
            signing_key = jwks.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256", "ES256"],
                issuer=settings.jwt_issuer if settings.jwt_issuer else None,
                audience=settings.jwt_audience if settings.jwt_audience else None,
                leeway=settings.jwt_leeway_seconds,
                options={
                    "verify_aud": bool(settings.jwt_audience),
                    "verify_iss": bool(settings.jwt_issuer),
                },
            )
        except jwt.PyJWTError as e:
            logger.debug("JWT JWKS decode failed: %s", e)
            raise ValueError("invalid_token") from e

    uid_claim = settings.jwt_user_id_claim
    sub = payload.get(uid_claim) or payload.get("sub")
    if not sub or not str(sub).strip():
        raise ValueError("invalid_token: missing user id claim")

    tenant = resolve_tenant_claim(payload, settings.jwt_tenant_claim)

    if settings.jwt_require_scope_check:
        try:
            enforce_scopes(payload, settings.required_scope_list)
        except PermissionError as e:
            raise PermissionError(str(e)) from e

    return Principal(user_id=str(sub).strip(), raw_claims=payload, tenant_from_token=tenant)
