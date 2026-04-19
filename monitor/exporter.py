"""Data Exporter layer.

ExportDispatcher fans out each DataRecord to every registered Exporter.
FileExporter is the always-on default (JSONL to disk); other transports
(MQTT, Socket, ...) plug into the same interface.
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from pathlib import Path

from data_record import DataRecord


class Exporter(ABC):
    """Every exporter implements this three-method interface."""

    @abstractmethod
    def export(self, record: DataRecord) -> None: ...

    def flush(self) -> None:
        return

    def close(self) -> None:
        return


class FileExporter(Exporter):
    """Append each record as one JSON line to <output_dir>/<session_id>.jsonl."""

    def __init__(
        self,
        output_dir: str,
        session_id: str,
        flush_every: int = 1,
    ):
        self.path = Path(output_dir) / f"{session_id}.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._f = self.path.open("a", encoding="utf-8")
        self._lock = threading.Lock()
        self._written = 0
        self.flush_every = max(1, int(flush_every))

    def export(self, record: DataRecord) -> None:
        line = record.to_json()
        with self._lock:
            self._f.write(line + "\n")
            self._written += 1
            if self._written % self.flush_every == 0:
                self._f.flush()

    def flush(self) -> None:
        with self._lock:
            if not self._f.closed:
                self._f.flush()

    def close(self) -> None:
        with self._lock:
            if not self._f.closed:
                self._f.flush()
                self._f.close()


class ExportDispatcher:
    """Owns the active exporter list plus a plugin registry (name -> class)."""

    def __init__(self):
        self._exporters: list[Exporter] = []
        self._registry: dict[str, type[Exporter]] = {}

    def register(self, name: str, exporter_cls: type[Exporter]) -> None:
        self._registry[name] = exporter_cls

    def has(self, name: str) -> bool:
        return name in self._registry

    def build(self, name: str, **kwargs) -> Exporter:
        if name not in self._registry:
            raise KeyError(f"Unknown exporter: {name}")
        return self._registry[name](**kwargs)

    def add(self, exporter: Exporter) -> None:
        self._exporters.append(exporter)

    def dispatch(self, record: DataRecord) -> None:
        for e in self._exporters:
            try:
                e.export(record)
            except Exception as ex:
                print(
                    f"[ExportDispatcher] exporter {type(e).__name__} export failed: {ex}",
                    flush=True,
                )

    def flush_all(self) -> None:
        for e in self._exporters:
            try:
                e.flush()
            except Exception:
                pass

    def close_all(self) -> None:
        for e in self._exporters:
            try:
                e.close()
            except Exception:
                pass
