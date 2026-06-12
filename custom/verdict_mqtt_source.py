"""Adapt MQTT Verdict JSON messages into DataRecords for aggregation demos."""

from __future__ import annotations

import json
import time
from typing import Any

from data_record import DataRecord
from source_mqtt import MQTTSource


class VerdictMQTTSource(MQTTSource):
    def _on_message(self, client, userdata, message):
        if self._exporter is None:
            return
        try:
            verdict = json.loads(message.payload.decode("utf-8"))
            topic = str(getattr(message, "topic", "verdict"))
            record = DataRecord(
                session_id=str(verdict.get("monitor_session_id", "")),
                record_id=f"{topic}:{time.time_ns()}",
                source_type="verdict",
                source_name=topic,
                timestamp=float(verdict.get("timestamp", time.time())),
                data=verdict,
            )
            self._exporter.export(record)
            self._received += 1
        except Exception:
            return
