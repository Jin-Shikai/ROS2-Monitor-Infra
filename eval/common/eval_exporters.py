"""Evaluation-owned exporters.

The framework's built-in verdict exporters do not record *when* a verdict
was emitted (ThresholdVerdict stamps verdicts with the timestamp of the
triggering input record). For latency measurements the evaluation needs the
wall-clock time at which the verdict reached its exporter, so this module
provides a drop-in file exporter that wraps each verdict line with an
`emitted_at` field.

Referenced from runtime YAML as:

    exporters:
      - type: eval.common.eval_exporters:TimestampedVerdictFileExporter
        path: verdicts_{session_id}.jsonl

Requires the standard launch recipe (cwd = repository root), which puts the
repo root on sys.path so the `eval.common` package resolves, and monitor/
on sys.path so `verdict_exporters` resolves.
"""

from __future__ import annotations

import json
import time

from verdict import Verdict
from verdict_exporters import VerdictFileExporter


class TimestampedVerdictFileExporter(VerdictFileExporter):
    """VerdictFileExporter that writes each verdict as one JSON line with an
    additional `emitted_at` wall-clock field (time.time(), seconds), measured
    when the verdict reaches this exporter.

    Detection latency = emitted_at - input DataRecord.timestamp (valid on a
    single host; across hosts subtract the measured clock offset).
    """

    def export(self, record: Verdict) -> None:
        line = {"emitted_at": time.time(), **json.loads(record.to_json())}
        with self._lock:
            if self._f.closed:
                return
            self._f.write(json.dumps(line) + "\n")
            self._written += 1
            if self._written % self.flush_every == 0:
                self._f.flush()
