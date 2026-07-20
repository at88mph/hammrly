from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any, Optional

import redis
from redis.exceptions import ResponseError, TimeoutError

from hammrly_orchestrator.config import Settings
from hammrly_orchestrator.envelope import EnvelopeParseError, parse_stream_payload, validate_campaign_envelope_minimal
from hammrly_orchestrator.listener import PAYLOAD_FIELD
from hammrly_orchestrator.redis_client import create_redis_client

logger = logging.getLogger(__name__)


class CampaignQueueListener:
    """Redis consumer for campaign expansion envelopes."""

    def __init__(
        self,
        settings: Settings,
        *,
        on_campaign: Callable[[dict[str, Any], str], None] | None = None,
        external_shutdown: Optional[threading.Event] = None,
    ) -> None:
        self._settings = settings
        self._on_campaign = on_campaign
        self._stop = threading.Event()
        self._external_shutdown = external_shutdown

    def _should_stop(self) -> bool:
        if self._stop.is_set():
            return True
        return bool(self._external_shutdown and self._external_shutdown.is_set())

    def stop(self) -> None:
        self._stop.set()

    def run_forever(self) -> None:
        if self._on_campaign is None:
            raise RuntimeError("CampaignQueueListener requires on_campaign handler")

        client = create_redis_client(self._settings)
        stream = self._settings.campaign_stream_key
        group = self._settings.redis_consumer_group
        consumer = f"{self._settings.redis_consumer_name}-campaign"

        try:
            self._ensure_consumer_group(client, stream, group)
        except ResponseError:
            logger.exception("Failed to ensure campaign consumer group")
            raise

        logger.info(
            "Campaign listener stream=%r group=%r consumer=%r",
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
                continue
            except ResponseError:
                logger.exception("campaign XREADGROUP failed")
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
            logger.error("campaign message_id=%s missing payload field", mid)
            return

        try:
            data = parse_stream_payload(raw)
            validate_campaign_envelope_minimal(
                data,
                accepted_schema_major=self._settings.accepted_schema_major,
            )
        except EnvelopeParseError as e:
            logger.warning("campaign message_id=%s parse error: %s", mid, e)
            return

        try:
            self._on_campaign(data, mid)
        except Exception:
            logger.exception("campaign message_id=%s handler failed", mid)
            return

        try:
            client.xack(stream, group, message_id)
        except ResponseError:
            logger.exception("campaign message_id=%s XACK failed", mid)

    @staticmethod
    def _ensure_consumer_group(client: redis.Redis, stream: str, group: str) -> None:
        try:
            client.xgroup_create(name=stream, groupname=group, id="$", mkstream=True)
            logger.info("Created consumer group %r on stream %r", group, stream)
        except ResponseError as e:
            if "BUSYGROUP" in str(e):
                return
            raise


def start_campaign_listener_background(
    settings: Settings,
    handler: Callable[[dict[str, Any], str], None],
    stop_event: threading.Event,
) -> threading.Thread:
    listener = CampaignQueueListener(settings, on_campaign=handler, external_shutdown=stop_event)

    def _run() -> None:
        listener.run_forever()

    t = threading.Thread(target=_run, name="campaign-listener", daemon=True)
    t.start()
    return t
