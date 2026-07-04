"""Transports for DSL-ready records — let a converter and its consuming
VerdictService run on separate hosts.

A DataConverter emits a JSON-serializable record (in practice a dict; see
`custom/*_converter.py`). In-process wiring feeds that record straight into a
`VerdictExporter`. To split the two stages across machines, the converter host
publishes the DSL record through a dsl `outputs:` endpoint, and the verdict
host receives it through a dsl `inputs:` endpoint routed to the verdict's
entry dispatcher.

Two built-in carriers exist, mirrored on both ends:

  * `mqtt` — one JSON line per record on a single configurable topic
    (`DslRecordMQTTExporter` / `DslRecordMQTTSource`);
  * `file` — one JSON line per record appended to a JSONL path
    (`DslRecordFileExporter` / `DslRecordFileSource`), usable across hosts via
    a shared mount, or single-host for archiving and replay.

User-defined carriers are referenced by `type: module.path:ClassName`. As
elsewhere, a missing `paho-mqtt` degrades to a silent no-op so the module
stays importable in test environments.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, cast

from exporter import Exporter
from plugins import resolve_plugin_class
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


class DslRecordFileExporter(Exporter[Any]):
    """Append each DSL-ready record as one JSON line to `path`."""

    def __init__(self, path: str, flush_every: int = 1):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._f = self.path.open("a", encoding="utf-8")
        self._lock = threading.Lock()
        self._written = 0
        self.flush_every = max(1, int(flush_every))

    def export(self, record: Any) -> None:
        line = json.dumps(record, default=str, ensure_ascii=False)
        with self._lock:
            if self._f.closed:
                return
            self._f.write(line + "\n")
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


class DslRecordFileSource(Source[Any]):
    """Replay DSL records from a JSONL file.

    With `follow: true` the source keeps reading appended lines (tail -f
    semantics), which makes a shared file usable as a live cross-host link.
    Without it the file is read once (optionally in a `loop`) for offline
    replay.
    """

    def __init__(
        self,
        path: str,
        interval_sec: float = 0.0,
        loop: bool = False,
        follow: bool = False,
        poll_sec: float = 0.2,
    ):
        self.path = Path(path)
        self.interval_sec = max(0.0, float(interval_sec))
        self.loop = bool(loop)
        self.follow = bool(follow)
        self.poll_sec = max(0.05, float(poll_sec))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self, exporter: Exporter[Any]) -> None:
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, args=(exporter,), name="dsl-file-source", daemon=True
        )
        self._thread.start()

    def _run(self, exporter: Exporter[Any]) -> None:
        while not self._stop.is_set() and self.follow and not self.path.exists():
            self._stop.wait(self.poll_sec)
        if not self.path.exists():
            logger.error("DSL replay file does not exist: %s", self.path)
            return
        while not self._stop.is_set():
            with self.path.open("r", encoding="utf-8") as stream:
                while not self._stop.is_set():
                    line = stream.readline()
                    if not line:
                        if self.follow:
                            self._stop.wait(self.poll_sec)
                            continue
                        break
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        exporter.export(json.loads(line))
                    except Exception as ex:
                        logger.warning("Skipping invalid DSL record: %s", ex)
                    if self.interval_sec:
                        self._stop.wait(self.interval_sec)
            if not self.loop:
                return

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None


DSL_EXPORTER_REGISTRY: dict[str, type[Exporter]] = {
    "mqtt": DslRecordMQTTExporter,
    "file": DslRecordFileExporter,
}

DSL_SOURCE_REGISTRY: dict[str, type[Source]] = {
    "mqtt": DslRecordMQTTSource,
    "file": DslRecordFileSource,
}


def resolve_dsl_exporter_class(type_str: str) -> type[Exporter]:
    return resolve_plugin_class(type_str, DSL_EXPORTER_REGISTRY, Exporter, "dsl exporter")


def resolve_dsl_source_class(type_str: str) -> type[Source]:
    return resolve_plugin_class(type_str, DSL_SOURCE_REGISTRY, Source, "dsl source")
