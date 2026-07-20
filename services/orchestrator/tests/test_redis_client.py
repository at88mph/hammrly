from hammrly_orchestrator.redis_client import redis_socket_timeout_sec


def test_redis_socket_timeout_exceeds_default_block_ms() -> None:
    # Default HAMMRLY_REDIS_BLOCK_MS is 5000; must be > 5s client default + block window.
    assert redis_socket_timeout_sec(5000) > 5.0
    assert redis_socket_timeout_sec(5000) == 10.0
