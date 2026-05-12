"""Converter for the `/cmd_vel` speed-limit property.

Pulls `twist.linear.x` out of incoming records and hands a flat
`{"speed": ..., "_timestamp": ...}` dict downstream. Source-name
filtering is handled by the framework via the YAML `inputs:` key on
the converter spec, so this class can stay pure projection logic.
"""

from __future__ import annotations

from data_record import DataRecord
from converter import DataConverter
from transformer import _get_path


PROPERTY_ID = "cmd_vel_speed_limit"


class CmdVelSpeedConverter(DataConverter):
    name = "CmdVelSpeedConverter"

    def convert(self, record: DataRecord) -> dict | None:
        # FieldExtractor produces flat dot-keyed dicts; raw records use
        # nested dicts. Support both so this converter survives a
        # config edit that removes the FieldExtractor stage.
        path = "twist.linear.x"
        if path in record.data:
            speed = record.data[path]
        else:
            found, speed = _get_path(record.data, path)
            if not found:
                return None
        return {
            "speed": speed,
            "_source_name": record.source_name,
            "_timestamp": record.timestamp,
            "_property_id": PROPERTY_ID,
        }
