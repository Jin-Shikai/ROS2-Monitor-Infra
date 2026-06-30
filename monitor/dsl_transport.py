"""Transport for DSL-ready records — lets a converter and its paired
VerdictService run on separate hosts.

A DataConverter emits a JSON-serializable record (in practice a dict; see
`custom/*_converter.py`). `build_converter_chain` normally feeds that record
straight into an in-process `VerdictExporter`. To split the two stages across
machines, the converter host publishes the DSL record over MQTT with
`DslRecordMQTTExporter`, and the verdict host receives it with
`DslRecordMQTTSource` and feeds it into the verdict stage's `dsl_dispatcher`.

    converter host                              verdict host
      Source[DataRecord]                          DslRecordMQTTSource
        -> ConverterExporter                        -> dsl_dispatcher
             -> Dispatcher[Any]                          -> VerdictExporter
                  -> DslRecordMQTTExporter --.              -> Dispatcher[Verdict]
                                              \           ^
                                               MQTT broker

This mirrors `exporter_mqtt.MQTTExporter` / `source_mqtt.MQTTSource` (which
carry DataRecords), but the payload here is the converter's DSL record sent on
a single configurable topic. As elsewhere, a missing `paho-mqtt` degrades to a
silent no-op so the module stays importable in test environments.
"""

from __future__ import annotations

import json
import logging
from typing import Any, cast

from exporter import Exporter
from source import Source

logger = logging.getLogger(__name__)

try:
    import paho.mqtt.client as mqtt
    _HAS_PAHO = True
except ImportError:
    mqtt = None  # type: ignore[assignment]
    _HAS_PAHO = False


def _new_client(client_id: str):
    mqtt_module = cast(Any, mqtt)
    return mqtt_module.Client(
        callback_api_version=mqtt_module.CallbackAPIVersion.VERSION2,
        client_id=client_id,
    )


class DslRecordMQTTExporter(Exporter[Any]):
    """Publish each DSL-ready record as one JSON line to a single MQTT topic.

    Non-blocking `connect_async()` + `loop_start()` lifecycle, identical to the
    other MQTT exporters in this project.
    """

    def __init__(
        self,
        topic: str,
        broker: str = "localhost",
        port: int = 1883,
        qos: int = 1,
        keepalive: int = 60,
        max_queued_messages: int = 1000,
        client_id: str = "",
        client: Any | None = None,
    ):
        self.topic = topic
        self.broker = broker
        self.port = int(port)
        self.qos = int(qos)
        self.keepalive = int(keepalive)
        self._published = 0

        if client is not None:
            self._client = client
            self._owns_client = False
            return

        if not _HAS_PAHO:
            logger.warning(
                "paho-mqtt not installed; DslRecordMQTTExporter falling back to no-op."
            )
            self._client = None
            self._owns_client = False
            return

        self._client = _new_client(client_id)
        self._client.max_queued_messages_set(int(max_queued_messages))
        self._client.on_connect = self._on_connect
        self._owns_client = True
        try:
            self._client.connect_async(self.broker, self.port, self.keepalive)
            self._client.loop_start()
        except Exception as ex:
            logger.error("DslRecordMQTTExporter failed to start network loop: %s", ex)

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            logger.info(
                "DslRecordMQTTExporter connected to %s:%d (topic=%s)",
                self.broker, self.port, self.topic,
            )
        else:
            logger.warning("DslRecordMQTTExporter connect failed: rc=%s", reason_code)

    def export(self, record: Any) -> None:
        if self._client is None:
            return
        try:
            payload = json.dumps(record, default=str, ensure_ascii=False)
            self._client.publish(self.topic, payload, qos=self.qos)
            self._published += 1
        except Exception as ex:
            logger.warning("DslRecordMQTTExporter publish failed on %s: %s", self.topic, ex)

    def close(self) -> None:
        if self._client is None or not self._owns_client:
            return
        try:
            self._client.loop_stop()
            self._client.disconnect()
        except Exception as ex:
            logger.warning("DslRecordMQTTExporter close error: %s", ex)


class DslRecordMQTTSource(Source[Any]):
    """Subscribe to one MQTT topic and push each JSON payload, parsed back into
    a DSL-ready record (dict), to the downstream `Exporter[Any]` — typically the
    verdict stage's `dsl_dispatcher`.

    Mirror image of `DslRecordMQTTExporter`; counterpart of `source_mqtt.MQTTSource`
    but yields the raw DSL dict rather than a `DataRecord`.
    """

    def __init__(
        self,
        topic: str,
        broker: str = "localhost",
        port: int = 1883,
        qos: int = 1,
        keepalive: int = 60,
        client_id: str = "",
        client: Any | None = None,
    ):
        self.topic = topic
        self.broker = broker
        self.port = int(port)
        self.qos = int(qos)
        self.keepalive = int(keepalive)
        self._exporter: Exporter[Any] | None = None
        self._received = 0

        if client is not None:
            self._client = client
            self._owns_client = False
            return

        if not _HAS_PAHO:
            logger.warning(
                "paho-mqtt not installed; DslRecordMQTTSource falling back to no-op."
            )
            self._client = None
            self._owns_client = False
            return

        self._client = _new_client(client_id)
        self._owns_client = True

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            logger.info(
                "DslRecordMQTTSource connected to %s:%d, subscribing %s",
                self.broker, self.port, self.topic,
            )
            client.subscribe(self.topic, qos=self.qos)
        else:
            logger.warning("DslRecordMQTTSource connect failed: rc=%s", reason_code)

    def _on_message(self, client, userdata, message):
        if self._exporter is None:
            return
        try:
            record = json.loads(message.payload.decode("utf-8"))
        except Exception as ex:
            logger.warning(
                "DslRecordMQTTSource cannot parse message on %s: %s",
                getattr(message, "topic", "?"), ex,
            )
            return
        try:
            self._exporter.export(record)
            self._received += 1
        except Exception as ex:
            logger.error("DslRecordMQTTSource downstream export error: %s", ex)

    def start(self, exporter: Exporter[Any]) -> None:
        self._exporter = exporter
        if self._client is None:
            return
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        if self._owns_client:
            try:
                self._client.connect_async(self.broker, self.port, self.keepalive)
                self._client.loop_start()
            except Exception as ex:
                logger.error("DslRecordMQTTSource failed to start network loop: %s", ex)

    def stop(self) -> None:
        if self._client is None or not self._owns_client:
            return
        try:
            self._client.loop_stop()
            self._client.disconnect()
        except Exception as ex:
            logger.warning("DslRecordMQTTSource stop error: %s", ex)
