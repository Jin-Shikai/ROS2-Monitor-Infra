"""MQTT Exporter — interface stub for Phase 4.

The class is wired into the exporter registry so config.yaml can already
reference `type: mqtt`. Actual publish is deferred until paho-mqtt is added
and the broker-side design is finalized.
"""

from __future__ import annotations

import logging

from data_record import DataRecord
from exporter import Exporter

logger = logging.getLogger(__name__)

try:
    import paho.mqtt.client as _mqtt  # noqa: F401
    _HAS_PAHO = True
except ImportError:
    _HAS_PAHO = False


class MQTTExporter(Exporter):
    """Phase-4 stub. Accepts configuration, logs a warning, drops records."""

    def __init__(
        self,
        broker: str = "localhost",
        port: int = 1883,
        topic_prefix: str = "monitor/",
        qos: int = 0,
    ):
        self.broker = broker
        self.port = int(port)
        self.topic_prefix = topic_prefix
        self.qos = int(qos)
        if not _HAS_PAHO:
            logger.warning(
                "paho-mqtt not installed; MQTTExporter is a no-op until Phase 4."
            )
        else:
            logger.info(
                "MQTTExporter configured (broker=%s:%d, topic_prefix=%s); "
                "publish behavior deferred to Phase 4.",
                self.broker, self.port, self.topic_prefix,
            )

    def export(self, record: DataRecord) -> None:
        # Phase 4 plan: publish record.to_json() to
        # f"{self.topic_prefix}{record.source_name.lstrip('/')}" with self.qos.
        return
