"""MQTTSource — subscribe to an MQTT broker and feed DataRecords into a sink.

This is the verdict-side inbound adapter; mirror image of MQTTExporter on
the monitor side. Each MQTT message payload is parsed with
`DataRecord.from_json()` and forwarded to the configured sink (typically
`Dispatcher.dispatch`).

Falls back to a no-op when paho-mqtt is missing, so the module can still be
imported in test environments without the dependency installed.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from data_record import DataRecord
from source import Source

logger = logging.getLogger(__name__)

try:
    import paho.mqtt.client as mqtt
    _HAS_PAHO = True
except ImportError:
    mqtt = None  # type: ignore[assignment]
    _HAS_PAHO = False


class MQTTSource(Source[DataRecord]):
    def __init__(
        self,
        broker: str = "localhost",
        port: int = 1883,
        topic_filter: str = "monitor/#",
        qos: int = 1,
        keepalive: int = 60,
        client_id: str = "",
        client: Any | None = None,
    ):
        self.broker = broker
        self.port = int(port)
        self.topic_filter = topic_filter
        self.qos = int(qos)
        self.keepalive = int(keepalive)
        self._sink: Callable[[DataRecord], None] | None = None
        self._received = 0

        if client is not None:
            self._client = client
            self._owns_client = False
            return

        if not _HAS_PAHO:
            logger.warning(
                "paho-mqtt not installed; MQTTSource falling back to no-op."
            )
            self._client = None
            self._owns_client = False
            return

        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
        )
        self._owns_client = True

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        # paho v2 passes a ReasonCode object; v1 passed an int. Both compare
        # equal to 0 on success, so avoid int() casting (ReasonCode rejects it).
        if reason_code == 0:
            logger.info(
                "MQTTSource connected to %s:%d, subscribing %s",
                self.broker, self.port, self.topic_filter,
            )
            client.subscribe(self.topic_filter, qos=self.qos)
        else:
            logger.warning("MQTTSource connect failed: rc=%s", reason_code)

    def _on_message(self, client, userdata, message):
        if self._sink is None:
            return
        try:
            payload = message.payload.decode("utf-8")
            record = DataRecord.from_json(payload)
        except Exception as ex:
            logger.warning(
                "MQTTSource cannot parse message on %s: %s",
                getattr(message, "topic", "?"), ex,
            )
            return
        try:
            self._sink(record)
            self._received += 1
        except Exception as ex:
            logger.error("MQTTSource sink error: %s", ex)

    def start(self, sink: Callable[[DataRecord], None]) -> None:
        self._sink = sink
        if self._client is None:
            return
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        if self._owns_client:
            try:
                self._client.connect_async(self.broker, self.port, self.keepalive)
                self._client.loop_start()
            except Exception as ex:
                logger.error("MQTTSource failed to start network loop: %s", ex)

    def stop(self) -> None:
        if self._client is None or not self._owns_client:
            return
        try:
            self._client.loop_stop()
            self._client.disconnect()
        except Exception as ex:
            logger.warning("MQTTSource stop error: %s", ex)
