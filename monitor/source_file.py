"""Replay DataRecords from a JSONL file into a runner.

With `follow: true` the source keeps reading appended lines (tail -f
semantics), which makes a shared file usable as a live cross-host records
link. Without it the file is read once (optionally in a `loop`) for offline
replay.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from data_record import DataRecord
from exporter import Exporter
from source import Source

logger = logging.getLogger(__name__)


class FileReplaySource(Source[DataRecord]):
    def __init__(
        self,
        path: str,
        interval_sec: float = 0.0,
        loop: bool = False,
        follow: bool = False,
        poll_sec: float = 0.2,
    ):
        self.path = Path(path)
        self.interval_sec = max(0.0, float(interval_sec))
        self.loop = bool(loop)
        self.follow = bool(follow)
        self.poll_sec = max(0.05, float(poll_sec))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self, exporter: Exporter[DataRecord]) -> None:
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            args=(exporter,),
            name="file-replay-source",
            daemon=True,
        )
        self._thread.start()

    def _run(self, exporter: Exporter[DataRecord]) -> None:
        while not self._stop.is_set() and self.follow and not self.path.exists():
            self._stop.wait(self.poll_sec)
        if not self.path.exists():
            logger.error("Replay file does not exist: %s", self.path)
            return
        while not self._stop.is_set():
            with self.path.open("r", encoding="utf-8") as stream:
                while not self._stop.is_set():
                    line = stream.readline()
                    if not line:
                        if self.follow:
                            self._stop.wait(self.poll_sec)
                            continue
                        break
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        exporter.export(DataRecord.from_json(line))
                    except Exception as ex:
                        logger.warning("Skipping invalid replay record: %s", ex)
                    if self.interval_sec:
                        self._stop.wait(self.interval_sec)
            if not self.loop:
                return

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
