"""Demo `dsl_converter` — aggregates several velocity components into a single
linear-speed DSL record.

It reads a list of velocity-component field paths off a DataRecord and emits
their Euclidean magnitude as a plain dict, e.g.

    speed = sqrt(vx^2 + vy^2)

Because it returns a **dict** (dsl payload), it feeds a VerdictService directly
(see `custom.threshold_verdict:ThresholdVerdict`) — that output type is exactly
what makes it a `dsl_converter` rather than a `data_filter`. For the record->record
`data_filter` counterpart (which can chain into another converter), see
`custom.odom_speed_filter:OdomSpeedFilter`. Field paths tolerate both the nested
message shape and the flat dot-keyed shape a FieldExtractor produces.
"""

from __future__ import annotations

import math

from converter import DataConverter
from data_record import DataRecord
from transformer import _get_path


class SpeedAggregateFilter(DataConverter):
    """Compute a magnitude from one or more numeric component fields.

    Constructor kwargs (all optional):
      * `components`   — list of dot-path field names to combine. Default is the
                         odom planar velocity `[linear.x, linear.y]`.
      * `output_field` — key the magnitude is written under. Default `speed`.
      * `property_id`  — `_property_id` tag added to the emitted record.
      * `source_name`  — if set, only records from this source are converted.
                         Usually omitted: the YAML `inputs:` filter selects the
                         source instead.
    """

    name = "SpeedAggregateFilter"

    def __init__(
        self,
        components: list[str] | None = None,
        output_field: str = "speed",
        property_id: str = "linear_speed",
        source_name: str | None = None,
    ):
        self.components = list(components) if components else [
            "twist.twist.linear.x",
            "twist.twist.linear.y",
        ]
        self.output_field = output_field
        self.property_id = property_id
        self.source_name = source_name

    def convert(self, record: DataRecord) -> dict | None:
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
        return {
            self.output_field: speed,
            "_source_name": record.source_name,
            "_session_id": record.session_id,
            "_record_id": record.record_id,
            "_timestamp": record.timestamp,
            "_property_id": self.property_id,
        }
