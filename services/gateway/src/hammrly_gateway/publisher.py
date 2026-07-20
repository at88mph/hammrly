from __future__ import annotations

import json
import logging
from typing import Any

import redis.asyncio as redis

from hammrly_gateway.redis_async import maybe_await

logger = logging.getLogger(__name__)

PAYLOAD_FIELD = b"payload"


async def publish_envelope(client: redis.Redis, stream_key: str, envelope: dict[str, Any]) -> str:
    """XADD; returns Redis stream message id."""
    payload = json.dumps(envelope, separators=(",", ":"), default=str).encode("utf-8")
    msg_id = await maybe_await(client.xadd(stream_key, {PAYLOAD_FIELD: payload}))
    logger.info(
        "Published submission_id=%s job_id=%s stream_msg_id=%s",
        envelope.get("submission_id"),
        envelope.get("job_id"),
        msg_id,
    )
    return msg_id
