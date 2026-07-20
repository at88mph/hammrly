from __future__ import annotations

import redis

from hammrly_orchestrator.config import Settings

# redis-py 7+ defaults socket_timeout to 5s. XREADGROUP BLOCK must complete before
# the client-side read timeout (see redis/_defaults.py DEFAULT_SOCKET_TIMEOUT).
_SOCKET_TIMEOUT_MARGIN_SEC = 5.0
_DEFAULT_CONNECT_TIMEOUT_SEC = 10.0


def redis_socket_timeout_sec(block_ms: int) -> float:
    """Client read timeout that safely exceeds XREADGROUP BLOCK (milliseconds)."""
    return (block_ms / 1000.0) + _SOCKET_TIMEOUT_MARGIN_SEC


def create_redis_client(settings: Settings) -> redis.Redis:
    return redis.Redis.from_url(
        settings.redis_url,
        decode_responses=False,
        socket_timeout=redis_socket_timeout_sec(settings.redis_block_ms),
        socket_connect_timeout=_DEFAULT_CONNECT_TIMEOUT_SEC,
    )
