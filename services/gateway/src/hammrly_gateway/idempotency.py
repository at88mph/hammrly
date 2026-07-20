from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Optional

import redis.asyncio as redis

from hammrly_gateway.config import Settings
from hammrly_gateway.redis_async import maybe_await

logger = logging.getLogger(__name__)


@dataclass
class IdempotencyRecord:
    job_id: str
    submission_id: str
    body_hash: str


def _key(settings: Settings, idempotency_key: str) -> str:
    return f"{settings.idempotency_redis_prefix}{idempotency_key}"


async def get_completed(r: redis.Redis, settings: Settings, idempotency_key: str) -> Optional[IdempotencyRecord]:
    raw = await maybe_await(r.get(_key(settings, idempotency_key)))
    if not raw:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    if raw == "pending":
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("corrupt idempotency payload for key suffix")
        return None
    try:
        return IdempotencyRecord(
            job_id=str(data["job_id"]),
            submission_id=str(data["submission_id"]),
            body_hash=str(data["body_hash"]),
        )
    except (KeyError, TypeError):
        return None


async def is_pending(r: redis.Redis, settings: Settings, idempotency_key: str) -> bool:
    raw = await maybe_await(r.get(_key(settings, idempotency_key)))
    if raw is None:
        return False
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return raw == "pending"


async def try_claim(r: redis.Redis, settings: Settings, idempotency_key: str) -> bool:
    """Returns True if this instance holds the claim (SET NX)."""
    ok = await maybe_await(
        r.set(
            _key(settings, idempotency_key),
            "pending",
            nx=True,
            ex=settings.idempotency_lock_seconds,
        )
    )
    return bool(ok)


async def release_claim(r: redis.Redis, settings: Settings, idempotency_key: str) -> None:
    await maybe_await(r.delete(_key(settings, idempotency_key)))


async def save_result(
    r: redis.Redis,
    settings: Settings,
    idempotency_key: str,
    *,
    job_id: str,
    submission_id: str,
    body_hash: str,
) -> None:
    payload = json.dumps(
        {"job_id": job_id, "submission_id": submission_id, "body_hash": body_hash},
        separators=(",", ":"),
    )
    await maybe_await(r.set(_key(settings, idempotency_key), payload, ex=settings.idempotency_ttl_seconds))
