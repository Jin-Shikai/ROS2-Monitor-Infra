"""Typed YAML configuration shapes used by the monitor and verdict runner."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import yaml


def _plugin_parts(
    data: dict[str, Any] | None,
    *,
    reserved: set[str] | None = None,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    raw = dict(data or {})
    reserved_keys = {"type"} | set(reserved or set())
    return (
        str(raw.get("type", "")),
        {k: v for k, v in raw.items() if k not in reserved_keys},
        raw,
    )


@dataclass(frozen=True)
class PluginSpec:
    type: str
    kwargs: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExporterSpec(PluginSpec):
    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ExporterSpec":
        type_name, kwargs, raw = _plugin_parts(data)
        return cls(type=type_name, kwargs=kwargs, raw=raw)


@dataclass(frozen=True)
class TransformerSpec(PluginSpec):
    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "TransformerSpec":
        type_name, kwargs, raw = _plugin_parts(data)
        return cls(type=type_name, kwargs=kwargs, raw=raw)


@dataclass(frozen=True)
class SourceSpec(PluginSpec):
    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "SourceSpec":
        type_name, kwargs, raw = _plugin_parts(data)
        return cls(type=type_name, kwargs=kwargs, raw=raw)


@dataclass(frozen=True)
class VerdictSpec:
    type: str
    kwargs: dict[str, Any]
    exporters: list[ExporterSpec]
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "VerdictSpec | None":
        if not data:
            return None
        raw = dict(data)
        exporters = [
            ExporterSpec.from_dict(e)
            for e in list(raw.get("exporters") or [])
        ]
        kwargs = {
            k: v for k, v in raw.items()
            if k not in {"type", "exporters"}
        }
        return cls(
            type=str(raw.get("type", "")),
            kwargs=kwargs,
            exporters=exporters,
            raw=raw,
        )


@dataclass(frozen=True)
class ConverterSpec:
    type: str
    kwargs: dict[str, Any]
    verdict: VerdictSpec | None
    inputs: list[str] | None = None
    output: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ConverterSpec":
        raw = dict(data or {})
        kwargs = {
            k: v for k, v in raw.items()
            if k not in {"type", "verdict", "output", "inputs"}
        }
        return cls(
            type=str(raw.get("type", "")),
            kwargs=kwargs,
            verdict=VerdictSpec.from_dict(raw.get("verdict")),
            inputs=raw.get("inputs"),
            output=raw.get("output"),
            raw=raw,
        )


@dataclass(frozen=True)
class MonitoredSourceSpec:
    name: str
    msg_type: str | None
    transformers: list[TransformerSpec]
    exporters: list[ExporterSpec]
    qos: int | None = None
    phases: list[str] | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "MonitoredSourceSpec":
        raw = dict(data or {})
        return cls(
            name=str(raw.get("name", "")),
            msg_type=raw.get("type"),
            transformers=[
                TransformerSpec.from_dict(t)
                for t in list(raw.get("transformers") or [])
            ],
            exporters=[
                ExporterSpec.from_dict(e)
                for e in list(raw.get("exporters") or [])
            ],
            qos=raw.get("qos"),
            phases=raw.get("phases"),
            raw=raw,
        )


@dataclass
class MonitorConfig:
    raw: dict[str, Any]
    output_dir: str = "./output"
    session_id_prefix: str = ""
    topics: list[MonitoredSourceSpec] = field(default_factory=list)
    services: list[MonitoredSourceSpec] = field(default_factory=list)
    actions: list[MonitoredSourceSpec] = field(default_factory=list)
    exporters: list[ExporterSpec] = field(default_factory=list)
    converters: list[ConverterSpec] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "MonitorConfig":
        raw = dict(data or {})
        monitor = raw.get("monitor", {}) or {}
        return cls(
            raw=raw,
            output_dir=monitor.get("output_dir", "./output"),
            session_id_prefix=monitor.get("session_id_prefix", ""),
            topics=[
                MonitoredSourceSpec.from_dict(s)
                for s in list(raw.get("topics") or [])
            ],
            services=[
                MonitoredSourceSpec.from_dict(s)
                for s in list(raw.get("services") or [])
            ],
            actions=[
                MonitoredSourceSpec.from_dict(s)
                for s in list(raw.get("actions") or [])
            ],
            exporters=[
                ExporterSpec.from_dict(e)
                for e in list(raw.get("exporters") or [])
            ],
            converters=[
                ConverterSpec.from_dict(c)
                for c in list(raw.get("converters") or [])
            ],
        )

    @classmethod
    def load(cls, yaml_path: str) -> "MonitorConfig":
        with open(yaml_path, "r", encoding="utf-8") as f:
            return cls.from_dict(yaml.safe_load(f) or {})


@dataclass
class RunnerConfig:
    output_dir: str
    converters: list[ConverterSpec]
    source: SourceSpec | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "RunnerConfig":
        raw = dict(data or {})
        monitor = raw.get("monitor", {}) or {}
        runner = raw.get("verdict_runner", {}) or {}
        source_raw = runner.get("source")
        return cls(
            output_dir=monitor.get("output_dir", "./output"),
            converters=[
                ConverterSpec.from_dict(c)
                for c in list(raw.get("converters") or [])
            ],
            source=SourceSpec.from_dict(source_raw) if source_raw else None,
        )

    @classmethod
    def load(cls, yaml_path: str) -> "RunnerConfig":
        with open(yaml_path, "r", encoding="utf-8") as f:
            return cls.from_dict(yaml.safe_load(f) or {})
