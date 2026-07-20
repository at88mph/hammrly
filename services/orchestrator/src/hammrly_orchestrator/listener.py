from __future__ import annotations

import logging
import signal
import threading
from collections.abc import Callable
from typing import Any, Optional

import redis
from redis.exceptions import ResponseError, TimeoutError

from hammrly_orchestrator.config import Settings
from hammrly_orchestrator.redis_client import create_redis_client
from hammrly_orchestrator.envelope import EnvelopeParseError, parse_stream_payload, validate_envelope_minimal

logger = logging.getLogger(__name__)

# Wire format: single stream field holding the JSON envelope (see contracts/job-submission/v1/README.md).
PAYLOAD_FIELD = b"payload"


class JobQueueListener:
    """
    Blocking Redis Streams consumer (XREADGROUP) for job submission envelopes.

    On handler success, messages are XACK'd. On handler failure or parse errors,
    messages are left pending for retry / operational follow-up.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        on_envelope: Callable[[dict[str, Any], str], None] | None = None,
        external_shutdown: Optional[threading.Event] = None,
    ) -> None:
        self._settings = settings
        self._on_envelope = on_envelope or self._default_handler
        self._stop = threading.Event()
        self._external_shutdown = external_shutdown

    def _should_stop(self) -> bool:
        if self._stop.is_set():
            return True
        return bool(self._external_shutdown and self._external_shutdown.is_set())

    @staticmethod
    def _default_handler(envelope: dict[str, Any], message_id: str) -> None:
        submission_id = envelope.get("submission_id")
        job_id = envelope.get("job_id")
        user_id = envelope.get("user_id")
        kind = envelope.get("workload", {}).get("kind")
        logger.info(
            "Received job submission message_id=%s job_id=%s submission_id=%s user_id=%s kind=%s",
            message_id,
            job_id,
            submission_id,
            user_id,
            kind,
        )

    def stop(self) -> None:
        self._stop.set()

    def run_forever(self) -> None:
        client = create_redis_client(self._settings)
        stream = self._settings.redis_stream_key
        group = self._settings.redis_consumer_group
        consumer = self._settings.redis_consumer_name

        try:
            self._ensure_consumer_group(client, stream, group)
        except ResponseError:
            logger.exception("Failed to ensure consumer group")
            raise

        logger.info(
            "Listening stream=%r group=%r consumer=%r",
            stream,
            group,
            consumer,
        )

        while not self._should_stop():
            try:
                messages = client.xreadgroup(
                    groupname=group,
                    consumername=consumer,
                    streams={stream: b">"},
                    count=self._settings.redis_read_count,
                    block=self._settings.redis_block_ms,
                )
            except TimeoutError:
                logger.warning(
                    "XREADGROUP timed out waiting for Redis (check socket_timeout vs HAMMRLY_REDIS_BLOCK_MS)"
                )
                continue
            except ResponseError:
                logger.exception("XREADGROUP failed")
                continue

            if not messages:
                continue

            for _stream_name, entries in messages:
                for message_id, fields in entries:
                    if self._should_stop():
                        break
                    self._process_one(client, stream, group, message_id, fields)

    def _process_one(
        self,
        client: redis.Redis,
        stream: str,
        group: str,
        message_id: bytes,
        fields: dict[bytes, bytes],
    ) -> None:
        mid = message_id.decode("utf-8", errors="replace")
        raw = fields.get(PAYLOAD_FIELD)
        if raw is None:
            logger.error("message_id=%s missing %r field; keys=%r", mid, PAYLOAD_FIELD.decode(), list(fields))
            return

        try:
            data = parse_stream_payload(raw)
            validate_envelope_minimal(data, accepted_schema_major=self._settings.accepted_schema_major)
        except EnvelopeParseError as e:
            logger.warning("message_id=%s parse error: %s", mid, e)
            return

        try:
            self._on_envelope(data, mid)
        except Exception:
            logger.exception("message_id=%s handler failed", mid)
            return

        try:
            client.xack(stream, group, message_id)
        except ResponseError:
            logger.exception("message_id=%s XACK failed", mid)

    @staticmethod
    def _ensure_consumer_group(client: redis.Redis, stream: str, group: str) -> None:
        try:
            client.xgroup_create(name=stream, groupname=group, id="$", mkstream=True)
            logger.info("Created consumer group %r on stream %r", group, stream)
        except ResponseError as e:
            if "BUSYGROUP" in str(e):
                return
            raise


def install_signal_handlers(listener: JobQueueListener, *extra_shutdown: threading.Event) -> None:
    def _handler(_signum: int, _frame: Any) -> None:
        listener.stop()
        for ev in extra_shutdown:
            ev.set()

    signal.signal(signal.SIGINT, _handler)
    signal.signal(signal.SIGTERM, _handler)
