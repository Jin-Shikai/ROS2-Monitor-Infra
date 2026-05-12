"""Verdict-side Exporters — concrete transports for emitted Verdicts.

Each class here is an `Exporter[Verdict]`, plugged into a
`Dispatcher[Verdict]` downstream of `VerdictExporter`. This is the
symmetric counterpart of `exporter.py` / `exporter_mqtt.py` on the
DataRecord side: one hierarchy, one term, fan-out + isolation reused.

User-defined verdict transports (ROS2 topic, socket, Slack, gRPC, ...)
are written as additional `Exporter[Verdict]` subclasses and referenced
in YAML by `type: module.path:ClassName`.
"""

from __future__ import annotations

import importlib
import logging
import threading
from pathlib import Path
from typing import Any

from exporter import Exporter, StdoutExporter
from verdict import Verdict

logger = logging.getLogger(__name__)

try:
    import paho.mqtt.client as mqtt
    _HAS_PAHO = True
except ImportError:
    mqtt = None  # type: ignore[assignment]
    _HAS_PAHO = False


class VerdictFileExporter(Exporter[Verdict]):
    """Append each Verdict as one JSON line to `path`."""

    def __init__(self, path: str, flush_every: int = 1):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._f = self.path.open("a", encoding="utf-8")
        self._lock = threading.Lock()
        self._written = 0
        self.flush_every = max(1, int(flush_every))

    def export(self, verdict: Verdict) -> None:
        with self._lock:
            if self._f.closed:
                return
            self._f.write(verdict.to_json() + "\n")
            self._written += 1
            if self._written % self.flush_every == 0:
                self._f.flush()

    def flush(self) -> None:
        with self._lock:
            if not self._f.closed:
                self._f.flush()

    def close(self) -> None:
        with self._lock:
            if not self._f.closed:
                self._f.flush()
                self._f.close()


class VerdictStdoutExporter(StdoutExporter[Verdict]):
    """Print each Verdict to stdout, prefixed `[Verdict]`."""

    def __init__(self):
        super().__init__(label="Verdict")


class VerdictMQTTExporter(Exporter[Verdict]):
    """Publish each Verdict as a JSON line to a single MQTT topic.

    Mirrors `exporter_mqtt.MQTTExporter`'s paho v2 lifecycle: non-blocking
    `connect_async()` + `loop_start()`, bounded outbound queue, no-paho
    fallback to a silent no-op. A future refactor can DRY the paho
    boilerplate via a shared client handle once a third caller appears.
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
        self.max_queued_messages = int(max_queued_messages)
        self._published = 0

        if client is not None:
            self._client = client
            self._owns_client = False
            return

        if not _HAS_PAHO:
            logger.warning(
                "paho-mqtt not installed; VerdictMQTTExporter falling back to no-op."
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
            logger.error("VerdictMQTTExporter failed to start network loop: %s", ex)

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        # paho v2 ReasonCode rejects int(); compare against 0 directly.
        if reason_code == 0:
            logger.info(
                "VerdictMQTTExporter connected to %s:%d (topic=%s)",
                self.broker, self.port, self.topic,
            )
        else:
            logger.warning("VerdictMQTTExporter connect failed: rc=%s", reason_code)

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        logger.warning("VerdictMQTTExporter disconnected: rc=%s", reason_code)

    def export(self, verdict: Verdict) -> None:
        if self._client is None:
            return
        try:
            self._client.publish(self.topic, verdict.to_json(), qos=self.qos)
            self._published += 1
        except Exception as ex:
            logger.warning("VerdictMQTTExporter publish failed on %s: %s", self.topic, ex)

    def close(self) -> None:
        if self._client is None or not self._owns_client:
            return
        try:
            self._client.loop_stop()
            self._client.disconnect()
        except Exception as ex:
            logger.warning("VerdictMQTTExporter close error: %s", ex)


VERDICT_EXPORTER_REGISTRY: dict[str, type[Exporter]] = {
    "file": VerdictFileExporter,
    "stdout": VerdictStdoutExporter,
    "mqtt": VerdictMQTTExporter,
}


def resolve_verdict_exporter_class(type_str: str) -> type[Exporter]:
    """Resolve a verdict exporter class from either a registry name
    (e.g. 'file', 'stdout', 'mqtt') or a 'module.path:ClassName' import
    string for user-defined exporters.
    """
    if ":" in type_str:
        module_path, _, class_name = type_str.partition(":")
        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)
        if not (isinstance(cls, type) and issubclass(cls, Exporter)):
            raise TypeError(
                f"{type_str} is not an Exporter subclass; cannot be used as a "
                f"verdict exporter."
            )
        return cls
    if type_str not in VERDICT_EXPORTER_REGISTRY:
        raise KeyError(
            f"Unknown verdict exporter type '{type_str}'. "
            f"Built-ins: {sorted(VERDICT_EXPORTER_REGISTRY)}. "
            f"For user-defined exporters use 'module.path:ClassName'."
        )
    return VERDICT_EXPORTER_REGISTRY[type_str]
