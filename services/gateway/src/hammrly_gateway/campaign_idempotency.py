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
class CampaignIdempotencyRecord:
    campaign_id: str
    body_hash: str
    item_count: Optional[int]
    status: str
    status_url: str


def _key(settings: Settings, idempotency_key: str) -> str:
    prefix = settings.campaign_idempotency_redis_prefix
    return f"{prefix}{idempotency_key}"


async def get_campaign_completed(
    r: redis.Redis,
    settings: Settings,
    idempotency_key: str,
) -> Optional[CampaignIdempotencyRecord]:
    raw = await maybe_await(r.get(_key(settings, idempotency_key)))
    if not raw:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    if raw == "pending":
        return None
    try:
        data = json.loads(raw)
        return CampaignIdempotencyRecord(
            campaign_id=str(data["campaign_id"]),
            body_hash=str(data["body_hash"]),
            item_count=data.get("item_count"),
            status=str(data.get("status", "accepted")),
            status_url=str(data["status_url"]),
        )
    except (KeyError, TypeError, json.JSONDecodeError):
        return None


async def is_campaign_pending(r: redis.Redis, settings: Settings, idempotency_key: str) -> bool:
    raw = await maybe_await(r.get(_key(settings, idempotency_key)))
    if raw is None:
        return False
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return raw == "pending"


async def try_campaign_claim(r: redis.Redis, settings: Settings, idempotency_key: str) -> bool:
    ok = await maybe_await(
        r.set(
            _key(settings, idempotency_key),
            "pending",
            nx=True,
            ex=settings.idempotency_lock_seconds,
        )
    )
    return bool(ok)


async def release_campaign_claim(r: redis.Redis, settings: Settings, idempotency_key: str) -> None:
    await maybe_await(r.delete(_key(settings, idempotency_key)))


async def save_campaign_result(
    r: redis.Redis,
    settings: Settings,
    idempotency_key: str,
    *,
    campaign_id: str,
    body_hash: str,
    item_count: Optional[int],
    status_url: str,
) -> None:
    payload = json.dumps(
        {
            "campaign_id": campaign_id,
            "body_hash": body_hash,
            "item_count": item_count,
            "status": "accepted",
            "status_url": status_url,
        },
        separators=(",", ":"),
    )
    await maybe_await(
        r.set(_key(settings, idempotency_key), payload, ex=settings.idempotency_ttl_seconds)
    )
