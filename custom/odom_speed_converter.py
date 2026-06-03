"""Demo converter for the `/odom` speed-limit property.

The deployment YAML only selects this class. The monitored source, field path
and property id are part of this custom implementation.
"""

from __future__ import annotations

from converter import DataConverter
from data_record import DataRecord
from transformer import _get_path


PROPERTY_ID = "odom_speed_limit"
SOURCE_NAME = "/odom"
SPEED_FIELD = "twist.twist.linear.x"


class OdomSpeedConverter(DataConverter):
    name = "OdomSpeedConverter"

    def convert(self, record: DataRecord) -> dict | None:
        if record.source_name != SOURCE_NAME:
            return None
        if SPEED_FIELD in record.data:
            speed = record.data[SPEED_FIELD]
        else:
            found, speed = _get_path(record.data, SPEED_FIELD)
            if not found:
                return None
        return {
            "speed": speed,
            "_source_name": record.source_name,
            "_session_id": record.session_id,
            "_record_id": record.record_id,
            "_timestamp": record.timestamp,
            "_property_id": PROPERTY_ID,
        }
