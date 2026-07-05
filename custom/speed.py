from __future__ import annotations

from typing import Any

from converter import DataConverter
from data_record import DataRecord
from transformer import _get_path


class CmdVelSpeedConverter(DataConverter):
    name = "CmdVelSpeedConverter"

    def convert(self, record: DataRecord) -> dict[str, Any] | None:
        if "linear.x" in record.data:
            speed = record.data["linear.x"]
        else:
            found, speed = _get_path(record.data, "linear.x")
            if not found:
                return None
        try:
            speed_value = float(speed)
        except (TypeError, ValueError):
            return None
        return {
            "speed": speed_value,
            "_property_id": "speed_check",
            "_source_name": record.source_name,
            "_session_id": record.session_id,
            "_record_id": record.record_id,
            "_timestamp": record.timestamp,
        }
