"""MQTT Exporter — Phase 4 real implementation.

Publishes DataRecords as JSON lines over MQTT. Topic naming:

    <topic_prefix><source_type>/<source_name without leading slash>

Session bookends (`session_start` / `session_end`) are published to:

    <topic_prefix>_session

Connection is non-blocking via `connect_async()` + `loop_start()`; paho
handles reconnects transparently using its built-in reconnect delay logic.
The bounded outbound queue is delegated to paho's `max_queued_messages_set`
(paho drops *new* messages when full — note this is not strict drop-oldest;
strict drop-oldest semantics would require an additional wrapper queue).

When `paho-mqtt` is not installed, MQTTExporter falls back to a no-op so
that the rest of the pipeline still functions and unit tests can run
without the dependency.
"""

from __future__ import annotations

import logging
from typing import Any

from data_record import DataRecord
from exporter import Exporter

logger = logging.getLogger(__name__)

try:
    import paho.mqtt.client as mqtt
    _HAS_PAHO = True
except ImportError:
    mqtt = None  # type: ignore[assignment]
    _HAS_PAHO = False


class MQTTExporter(Exporter[DataRecord]):
    def __init__(
        self,
        broker: str = "localhost",
        port: int = 1883,
        topic_prefix: str = "monitor/",
        qos: int = 1,
        keepalive: int = 60,
        max_queued_messages: int = 1000,
        publish_bookends: bool = True,
        client_id: str = "",
        client: Any | None = None,
    ):
        self.broker = broker
        self.port = int(port)
        self.topic_prefix = topic_prefix
        self.qos = int(qos)
        self.keepalive = int(keepalive)
        self.max_queued_messages = int(max_queued_messages)
        self.publish_bookends = bool(publish_bookends)
        self._published = 0

        if client is not None:
            self._client = client
            self._owns_client = False
            return

        if not _HAS_PAHO:
            logger.warning(
                "paho-mqtt not installed; MQTTExporter falling back to no-op."
            )
            self._client = None
            self._owns_client = False
            return

        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
        )
        self._client.max_queued_messages_set(self.max_queued_messages)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._owns_client = True
        try:
            self._client.connect_async(self.broker, self.port, self.keepalive)
            self._client.loop_start()
        except Exception as ex:
            logger.error("MQTTExporter failed to start network loop: %s", ex)

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        # paho v2 passes a ReasonCode object; v1 passed an int. Both compare
        # equal to 0 on success, so avoid int() casting (ReasonCode rejects it).
        if reason_code == 0:
            logger.info(
                "MQTTExporter connected to %s:%d (prefix=%s)",
                self.broker, self.port, self.topic_prefix,
            )
        else:
            logger.warning("MQTTExporter connect failed: rc=%s", reason_code)

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        logger.warning("MQTTExporter disconnected: rc=%s", reason_code)

    def _topic_for(self, record: DataRecord) -> str:
        if record._type != "data":
            return f"{self.topic_prefix}_session"
        st = record.source_type or "unknown"
        sn = (record.source_name or "").lstrip("/")
        if not sn:
            return f"{self.topic_prefix}{st}"
        return f"{self.topic_prefix}{st}/{sn}"

    def export(self, record: DataRecord) -> None:
        if record._type != "data" and not self.publish_bookends:
            return
        if self._client is None:
            return
        topic = self._topic_for(record)
        try:
            self._client.publish(topic, record.to_json(), qos=self.qos)
            self._published += 1
        except Exception as ex:
            logger.warning("MQTTExporter publish failed on %s: %s", topic, ex)

    def flush(self) -> None:
        # paho's loop thread drives the network layer; nothing to flush here.
        return

    def close(self) -> None:
        if self._client is None or not self._owns_client:
            return
        try:
            self._client.loop_stop()
            self._client.disconnect()
        except Exception as ex:
            logger.warning("MQTTExporter close error: %s", ex)
