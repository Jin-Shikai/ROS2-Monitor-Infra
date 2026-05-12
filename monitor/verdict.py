"""Verdict layer — framework abstractions only.

A VerdictService consumes a DSL-ready record (produced by some DataConverter)
and either returns a Verdict or returns None to remain silent. Real DSL
engines (LTL/STL/CTL/...) live outside the framework — see `custom/` for an
example implementation.

VerdictExporter wraps a VerdictService as an Exporter so it can be registered
on the downstream Dispatcher carrying DSL-ready records. Verdicts emitted by
the service are forwarded to a `sink` callable — typically the `.dispatch`
method of a `Dispatcher[Verdict]` whose member Exporters (file / stdout /
mqtt / user-defined) are configured per YAML.

  Dispatcher[Any] -> VerdictExporter -> VerdictService.evaluate() -> Verdict
                                                                       |
                                                                       v
                                                              Dispatcher[Verdict]
                                                                  |--> VerdictFileExporter
                                                                  |--> VerdictMQTTExporter
                                                                  `--> ... (user-pluggable)
"""

from __future__ import annotations

import importlib
import json
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from exporter import Exporter


@dataclass
class Verdict:
    """Outcome of evaluating a property against one DSL-ready record."""

    timestamp: float
    property_id: str
    result: bool                     # True = property holds; False = violation
    details: dict = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), default=str, ensure_ascii=False)


class VerdictService(ABC):
    """Evaluate a DSL-ready record against one or more properties.

    Return a Verdict when a property fires (either holds or is violated, per
    the service's semantics), or None to stay silent.
    """

    name: str = "VerdictService"

    @abstractmethod
    def evaluate(self, dsl_record: Any) -> Verdict | None: ...


class VerdictExporter(Exporter[Any]):
    """Adapter: presents a VerdictService as an Exporter on a Dispatcher[Any].

    When a Verdict is emitted, it is forwarded to `sink` (default: print to
    stdout). In production wiring `sink` is a `Dispatcher[Verdict].dispatch`,
    fanning out to any number of `Exporter[Verdict]` instances (file, mqtt,
    stdout, user-defined).
    """

    def __init__(
        self,
        service: VerdictService,
        sink: Callable[[Verdict], None] | None = None,
    ):
        self.service = service
        self.sink = sink or _default_sink

    def export(self, record: Any) -> None:
        verdict = self.service.evaluate(record)
        if verdict is not None:
            self.sink(verdict)


def _default_sink(verdict: Verdict) -> None:
    print(f"[Verdict] {verdict.to_json()}", flush=True)


def resolve_verdict_class(spec: str) -> type[VerdictService]:
    """Resolve a VerdictService class from a 'module.path:ClassName' import string.

    Example: 'custom.threshold_verdict:ThresholdVerdict'
    """
    if ":" not in spec:
        raise ValueError(
            f"Bad verdict spec '{spec}'. Expected 'module.path:ClassName' "
            f"(e.g. 'custom.threshold_verdict:ThresholdVerdict')."
        )
    module_path, _, class_name = spec.partition(":")
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    if not (isinstance(cls, type) and issubclass(cls, VerdictService)):
        raise TypeError(f"{spec} is not a VerdictService subclass")
    return cls
