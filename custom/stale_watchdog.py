"""Self-scheduled converter — emits when a source falls silent.

Demonstrates the converter lifecycle (`start(emit)` / `stop()`): a purely
reactive `convert()` can never fire on the *absence* of records, so the
watchdog runs its own timer thread and emits a DSL record once the watched
stream has been quiet longer than `timeout_sec`.

Pair with e.g. `custom.threshold_verdict:ThresholdVerdict`
(`field: silent_sec, op: ">", threshold: <timeout>`).
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

from converter import DataConverter
from data_record import DataRecord


class StaleWatchdogConverter(DataConverter):
    name = "StaleWatchdogConverter"

    def __init__(
        self,
        timeout_sec: float,
        property_id: str = "source_liveness",
        check_interval_sec: float | None = None,
    ):
        self.timeout_sec = float(timeout_sec)
        self.property_id = property_id
        self.check_interval_sec = float(check_interval_sec or max(0.05, self.timeout_sec / 4))
        self._last_seen: float | None = None
        self._fired = False
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def convert(self, record: DataRecord) -> Any | None:
        with self._lock:
            self._last_seen = time.monotonic()
            self._fired = False
        return None

    def start(self, emit: Callable[[Any], None]) -> None:
        self._stop.clear()

        def watch() -> None:
            while not self._stop.wait(self.check_interval_sec):
                with self._lock:
                    if self._last_seen is None or self._fired:
                        continue
                    silent = time.monotonic() - self._last_seen
                    if silent <= self.timeout_sec:
                        continue
                    self._fired = True
                emit({
                    "silent_sec": silent,
                    "_property_id": self.property_id,
                    "_timestamp": time.time(),
                })

        self._thread = threading.Thread(target=watch, name="stale-watchdog", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
