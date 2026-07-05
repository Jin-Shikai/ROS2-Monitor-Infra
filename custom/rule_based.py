"""Example DataConverter — copy and adapt for your DSL.

Demonstrates the minimal contract:
  - Subclass `DataConverter` and implement `convert(record) -> dsl_record | None`
  - `__init__` parameters become YAML keys under your `converters:` entry
  - Return None to skip a record (wrong source, missing field, ...)

Wire-up in monitor/config.yaml::

    converters:
      - type: custom.rule_based:RuleBasedConverter
        source_match: "^/odom$"
        field_map:
          velocity: twist.twist.linear.x
          position_x: pose.pose.position.x
        property_id: odom_speed
        verdict:
          type: custom.threshold:ThresholdVerdict
          property_id: odom_speed
          field: velocity
          op: ">"
          threshold: 0.5
          output: verdicts_{session_id}.jsonl

The `type:` value is `module.path:ClassName`. Relative imports work as long
as the project root is on PYTHONPATH (monitor_node.py adds the cwd).
"""

from __future__ import annotations

import re
from typing import Any

from data_record import DataRecord
from converter import DataConverter
from transformer import _get_path


class RuleBasedConverter(DataConverter):
    """Project a few DataRecord.data fields into a flat dict, keyed for downstream
    threshold-style verdict services. Records whose source_name doesn't match
    the regex are skipped.

    Output schema:
        {
          <user-defined keys from field_map>,
          "_source_name": str,
          "_timestamp": float,
          "_property_id": str (if configured),
        }

    Set `require_all=true` to drop records when any mapped field is missing.
    Default behaviour drops a record only when *no* field could be extracted.
    """

    name = "RuleBasedConverter"

    def __init__(
        self,
        source_match: str,
        field_map: dict[str, str],
        property_id: str | None = None,
        require_all: bool = False,
    ):
        self._pattern = re.compile(source_match)
        self.field_map = dict(field_map)
        self.property_id = property_id
        self.require_all = bool(require_all)

    def convert(self, record: DataRecord) -> dict | None:
        if not self._pattern.search(record.source_name):
            return None
        out: dict[str, Any] = {}
        for out_key, path in self.field_map.items():
            # FieldExtractor flattens to dot-notation keys (e.g. "twist.twist.linear.x"
            # is a literal key in record.data). Try a flat lookup first, fall back to
            # nested traversal for raw records that haven't been through FieldExtractor.
            if path in record.data:
                out[out_key] = record.data[path]
            else:
                found, value = _get_path(record.data, path)
                if found:
                    out[out_key] = value
                elif self.require_all:
                    return None
        if not out:
            return None
        out["_source_name"] = record.source_name
        out["_session_id"] = record.session_id
        out["_record_id"] = record.record_id
        out["_timestamp"] = record.timestamp
        if self.property_id is not None:
            out["_property_id"] = self.property_id
        return out
