"""Demo `data_filter` converter — DataRecord -> DataRecord.

A `data_filter` differs from a `dsl_converter` only in its output type: it emits
a `DataRecord` (records payload), so it can be **chained into another
converter** across a transport, whereas a `dsl_converter` emits a plain dict
(dsl payload) that only a VerdictService consumes.

`OdomSpeedFilter` does an aggregation: it reads velocity components off an
`/odom` record and reduces them to a single derived `speed` field, returning a
trimmed DataRecord carrying just that field. A downstream `dsl_converter` (e.g.
`custom.rule_based_converter:RuleBasedConverter` with `field_map: {speed: speed}`)
then projects it into the DSL record its paired verdict reads.
"""

from __future__ import annotations

import dataclasses
import math

from converter import DataConverter
from data_record import DataRecord
from transformer import _get_path


class OdomSpeedFilter(DataConverter):
    """Aggregate velocity components into a `speed` field, returning a record.

    Constructor kwargs (all optional):
      * `components`   — dot-path fields to combine. Default odom planar velocity.
      * `output_field` — key the magnitude is written under. Default `speed`.
      * `source_name`  — restrict to one source (usually the YAML `inputs:`
                         filter does this instead).
    """

    name = "OdomSpeedFilter"

    def __init__(
        self,
        components: list[str] | None = None,
        output_field: str = "speed",
        source_name: str | None = None,
    ):
        self.components = list(components) if components else [
            "twist.twist.linear.x",
            "twist.twist.linear.y",
        ]
        self.output_field = output_field
        self.source_name = source_name

    def convert(self, record: DataRecord) -> DataRecord | None:
        if self.source_name is not None and record.source_name != self.source_name:
            return None

        values: list[float] = []
        for path in self.components:
            if path in record.data:
                raw = record.data[path]
            else:
                found, raw = _get_path(record.data, path)
                if not found:
                    continue
            try:
                values.append(float(raw))
            except (TypeError, ValueError):
                continue

        if not values:
            return None

        speed = math.sqrt(sum(v * v for v in values))
        # A new DataRecord keeps the records payload contract: same identity,
        # trimmed data carrying only the derived quantity.
        return dataclasses.replace(record, data={self.output_field: speed})
