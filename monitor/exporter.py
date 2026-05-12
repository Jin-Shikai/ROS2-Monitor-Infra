"""Generic Exporter / Dispatcher transport layer.

Originally specific to DataRecord. Now parameterized over a record type T so
that the same infrastructure can carry DataRecords from the Collector side and
DSL-ready records produced by a DataConverter on the downstream side.

  Collector -> TransformerPipeline -> Dispatcher[DataRecord]
                                          |--> FileExporter[DataRecord]
                                          |--> MQTTExporter
                                          `--> ConverterExporter (adapter)
                                                   `--> Dispatcher[Any]
                                                          |--> VerdictExporter
                                                          `--> FileExporter[Any]
"""

from __future__ import annotations

import json
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable, Generic, TypeVar

T = TypeVar("T")


class Exporter(ABC, Generic[T]):
    """Three-method interface every exporter implements."""

    @abstractmethod
    def export(self, record: T) -> None: ...

    def flush(self) -> None:
        return

    def close(self) -> None:
        return


class FileExporter(Exporter[T], Generic[T]):
    """Append each record as one JSON line to <output_dir>/<session_id><suffix>.jsonl.

    Generic over T: DataRecord uses its own to_json(); arbitrary dicts fall
    back to json.dumps. A custom `serialize` overrides both.
    """

    def __init__(
        self,
        output_dir: str,
        session_id: str,
        flush_every: int = 1,
        filename_suffix: str = "",
        serialize: Callable[[T], str] | None = None,
    ):
        self.path = Path(output_dir) / f"{session_id}{filename_suffix}.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._f = self.path.open("a", encoding="utf-8")
        self._lock = threading.Lock()
        self._written = 0
        self.flush_every = max(1, int(flush_every))
        self._serialize = serialize or _default_serialize

    def export(self, record: T) -> None:
        line = self._serialize(record)
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


def _default_serialize(record: Any) -> str:
    if hasattr(record, "to_json"):
        return record.to_json()
    return json.dumps(record, default=str, ensure_ascii=False)


class StdoutExporter(Exporter[T], Generic[T]):
    """Print each record to stdout, prefixed by `label`.

    Generic over T: uses the same duck-typed serializer as FileExporter,
    so DataRecords, Verdicts, and plain dicts all work.
    """

    def __init__(
        self,
        label: str = "Record",
        serialize: Callable[[T], str] | None = None,
    ):
        self.label = label
        self._serialize = serialize or _default_serialize

    def export(self, record: T) -> None:
        print(f"[{self.label}] {self._serialize(record)}", flush=True)


class Dispatcher(Generic[T]):
    """Owns an exporter list plus a plugin registry (name -> class).

    Records go in via dispatch(); each registered Exporter gets its own
    try/except so a single bad exporter cannot take down the rest.
    """

    def __init__(self, label: str = "Dispatcher"):
        self._label = label
        self._exporters: list[Exporter[T]] = []
        self._registry: dict[str, type[Exporter[T]]] = {}

    def register(self, name: str, exporter_cls: type[Exporter[T]]) -> None:
        self._registry[name] = exporter_cls

    def has(self, name: str) -> bool:
        return name in self._registry

    def build(self, name: str, **kwargs) -> Exporter[T]:
        if name not in self._registry:
            raise KeyError(f"Unknown exporter: {name}")
        return self._registry[name](**kwargs)

    def add(self, exporter: Exporter[T]) -> None:
        self._exporters.append(exporter)

    def dispatch(self, record: T) -> None:
        for e in self._exporters:
            try:
                e.export(record)
            except Exception as ex:
                print(
                    f"[{self._label}] exporter {type(e).__name__} export failed: {ex}",
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


# Backward-compat alias for callers that still use the old name.
ExportDispatcher = Dispatcher
