"""Typed YAML configuration shapes used by monitor_node and node_runner."""

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
class EndpointSpec:
    """One inbound (`inputs:`) or outbound (`outputs:`) transport endpoint.

    `payload` selects the wire format: `records` carries DataRecords, `dsl`
    carries converter-produced DSL records. `type` is a built-in transport
    name (mqtt, file) or `module.path:ClassName`.
    """

    id: str
    payload: str
    type: str
    kwargs: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None, index: int = 0) -> "EndpointSpec":
        raw = dict(data or {})
        reserved = {"id", "payload", "type"}
        return cls(
            id=str(raw.get("id") or f"endpoint_{index}"),
            payload=str(raw.get("payload", "records")),
            type=str(raw.get("type", "")),
            kwargs={k: v for k, v in raw.items() if k not in reserved},
            raw=raw,
        )


@dataclass(frozen=True)
class VerdictSpec:
    type: str
    kwargs: dict[str, Any]
    exporters: list[ExporterSpec]
    id: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "VerdictSpec | None":
        if not data:
            return None
        raw = dict(data)
        params_raw = raw.get("params")
        params = params_raw if isinstance(params_raw, dict) else {}
        exporters = [
            ExporterSpec.from_dict(e)
            for e in list(raw.get("exporters") or [])
        ]
        kwargs = {
            k: v for k, v in raw.items()
            if k not in {"id", "type", "params", "exporters"}
        }
        kwargs.update(params)
        return cls(
            type=str(raw.get("type", "")),
            kwargs=kwargs,
            exporters=exporters,
            id=str(raw.get("id")) if raw.get("id") is not None else None,
            raw=raw,
        )


@dataclass(frozen=True)
class ConverterSpec:
    type: str
    kwargs: dict[str, Any]
    id: str | None = None
    inputs: list[str] | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ConverterSpec":
        raw = dict(data or {})
        params_raw = raw.get("params")
        params = params_raw if isinstance(params_raw, dict) else {}
        kwargs = {
            k: v for k, v in raw.items()
            if k not in {"id", "type", "params", "inputs"}
        }
        kwargs.update(params)
        return cls(
            type=str(raw.get("type", "")),
            kwargs=kwargs,
            id=str(raw.get("id")) if raw.get("id") is not None else None,
            inputs=raw.get("inputs"),
            raw=raw,
        )


@dataclass(frozen=True)
class RuntimeLinkSpec:
    from_ref: str
    to_ref: str
    id: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "RuntimeLinkSpec":
        raw = dict(data or {})
        return cls(
            from_ref=str(raw.get("from") or raw.get("from_ref") or ""),
            to_ref=str(raw.get("to") or raw.get("to_ref") or ""),
            id=str(raw.get("id")) if raw.get("id") is not None else None,
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


def _graph_fields(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "converters": [
            ConverterSpec.from_dict(c)
            for c in list(raw.get("converters") or [])
        ],
        "verdict_services": [
            v for v in (
                VerdictSpec.from_dict(s)
                for s in list(raw.get("verdict_services") or [])
            )
            if v is not None
        ],
        "links": [
            RuntimeLinkSpec.from_dict(l)
            for l in list(raw.get("links") or [])
        ],
        "outputs": [
            EndpointSpec.from_dict(o, index)
            for index, o in enumerate(list(raw.get("outputs") or []), start=1)
        ],
    }


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
    verdict_services: list[VerdictSpec] = field(default_factory=list)
    links: list[RuntimeLinkSpec] = field(default_factory=list)
    outputs: list[EndpointSpec] = field(default_factory=list)

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
            **_graph_fields(raw),
        )

    @classmethod
    def load(cls, yaml_path: str) -> "MonitorConfig":
        with open(yaml_path, "r", encoding="utf-8") as f:
            return cls.from_dict(yaml.safe_load(f) or {})


@dataclass
class RunnerConfig:
    output_dir: str
    inputs: list[EndpointSpec] = field(default_factory=list)
    converters: list[ConverterSpec] = field(default_factory=list)
    verdict_services: list[VerdictSpec] = field(default_factory=list)
    links: list[RuntimeLinkSpec] = field(default_factory=list)
    outputs: list[EndpointSpec] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "RunnerConfig":
        raw = dict(data or {})
        monitor = raw.get("monitor", {}) or {}
        return cls(
            output_dir=monitor.get("output_dir", "./output"),
            inputs=[
                EndpointSpec.from_dict(i, index)
                for index, i in enumerate(list(raw.get("inputs") or []), start=1)
            ],
            **_graph_fields(raw),
        )

    @classmethod
    def load(cls, yaml_path: str) -> "RunnerConfig":
        with open(yaml_path, "r", encoding="utf-8") as f:
            return cls.from_dict(yaml.safe_load(f) or {})
