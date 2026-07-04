"""Generation-request layer: project a deployment JSON into runtime YAML.

A request is a deployment model — physical ``hosts`` own executable
``runtimes`` (``ros2`` / ``monitor`` / ``converter`` / ``verdict_service``),
and ``links`` describe how runtimes on different hosts exchange ``records``
(DataRecords) or ``dsl`` (converter output) payloads over a transport
(``mqtt`` or ``file``).

The module does *not* re-implement the runtime. It only **projects** the
request onto the runtime YAML that `config_model.MonitorConfig` /
`RunnerConfig` parse:

    GenerationRequest --project()--> { host_id: GeneratedConfig(runtime YAML) }

Projection rules (one YAML per host, entrypoint chosen by the host's runtimes):

  * host with a ``monitor``                    -> ``monitor_node`` YAML;
    co-located converters/verdicts run in-process, cross-host converter
    output leaves through ``outputs:`` endpoints.
  * host with converters and/or verdicts only  -> ``node_runner`` YAML;
    any mix of inbound ``inputs:``, local graph wiring, and outbound
    ``outputs:`` runs in one process — there are no per-process roles.
  * ``ros2``-only host                         -> no file (it only supplies
    sources).

Same-host wiring is in-process and derived from ``output_to`` record ids
(converter) matching ``input_from`` (converter or verdict). Cross-host wiring
requires an explicit request link; both ends derive the same transport
namespace from the link, so writer and reader always agree.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import yaml


# --------------------------------------------------------------------------- #
# Request-layer model
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class TransportSpec:
    """A ``Link.transport``. ``kind`` selects the carrier; the rest are
    connection details the request may pin and an optional explicit ``topic``
    (otherwise derived)."""

    kind: str = "mqtt"
    broker: str = "localhost"
    port: int = 1883
    qos: int = 1
    topic: str | None = None          # explicit dsl topic (else derived)
    topic_prefix: str | None = None   # records namespace (else "monitor/")

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "TransportSpec":
        raw = dict(data or {})
        return cls(
            kind=str(raw.get("kind", "mqtt")),
            broker=str(raw.get("broker", "localhost")),
            port=int(raw.get("port", 1883)),
            qos=int(raw.get("qos", 1)),
            topic=raw.get("topic"),
            topic_prefix=raw.get("topic_prefix"),
        )


@dataclass(frozen=True)
class SourceSpec:
    """A monitorable ROS2 resource declared under a ``ros2`` runtime."""

    id: str
    source_kind: str  # "topic" | "service" | "action"
    name: str
    interface: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SourceSpec":
        return cls(
            id=str(data["id"]),
            source_kind=str(data.get("source_kind", "topic")),
            name=str(data.get("name", "")),
            interface=data.get("interface"),
        )


_RUNTIME_RESERVED = {
    "id", "kind", "sources", "subscribe",
    "converter", "class_path", "input_from", "output_to",
}


@dataclass(frozen=True)
class RuntimeSpec:
    """One executable runtime on a host. ``kind`` selects its shape; unknown
    fields are kept in ``params`` and forwarded as plugin constructor kwargs."""

    id: str
    kind: str
    sources: list[SourceSpec] = field(default_factory=list)
    subscribe: list[str] = field(default_factory=list)
    converter: str | None = None          # "data_filter" | "dsl_converter" (informative)
    class_path: str | None = None
    input_from: list[str] = field(default_factory=list)
    output_to: Any = None                 # converter: record id; verdict: outlets
    params: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RuntimeSpec":
        raw = dict(data)
        return cls(
            id=str(raw["id"]),
            kind=str(raw["kind"]),
            sources=[SourceSpec.from_dict(s) for s in raw.get("sources", []) or []],
            subscribe=list(raw.get("subscribe", []) or []),
            converter=raw.get("converter"),
            class_path=raw.get("class_path"),
            input_from=list(raw.get("input_from", []) or []),
            output_to=raw.get("output_to"),
            params={k: v for k, v in raw.items() if k not in _RUNTIME_RESERVED},
        )


@dataclass(frozen=True)
class HostSpec:
    id: str
    runtimes: list[RuntimeSpec] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HostSpec":
        return cls(
            id=str(data["id"]),
            runtimes=[RuntimeSpec.from_dict(r) for r in data.get("runtimes", []) or []],
        )


@dataclass(frozen=True)
class LinkSpec:
    id: str
    from_host: str
    to_host: str
    from_runtime: str
    to_runtime: str
    payload: str                          # "records" | "dsl"
    transport: TransportSpec

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LinkSpec":
        return cls(
            id=str(data.get("id", "")),
            from_host=str(data["from_host"]),
            to_host=str(data["to_host"]),
            from_runtime=str(data["from_runtime"]),
            to_runtime=str(data["to_runtime"]),
            payload=str(data.get("payload", "records")),
            transport=TransportSpec.from_dict(data.get("transport")),
        )


@dataclass(frozen=True)
class GenerationRequest:
    hosts: list[HostSpec]
    links: list[LinkSpec]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GenerationRequest":
        return cls(
            hosts=[HostSpec.from_dict(h) for h in data.get("hosts", []) or []],
            links=[LinkSpec.from_dict(l) for l in data.get("links", []) or []],
        )

    @classmethod
    def load(cls, json_path: str) -> "GenerationRequest":
        with open(json_path, "r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f))


# --------------------------------------------------------------------------- #
# Projection result
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class GeneratedConfig:
    """One generated runtime YAML plus how to run it."""

    host_id: str
    entrypoint: str                # "monitor_node" | "node_runner"
    config: dict[str, Any]

    @property
    def filename(self) -> str:
        return f"{self.host_id}.yaml"

    def run_command(self) -> str:
        cfg = f"<outdir>/{self.filename}"
        if self.entrypoint == "monitor_node":
            return f"python monitor/monitor_node.py -c {cfg}"
        return f"python monitor/node_runner.py -c {cfg}"


# --------------------------------------------------------------------------- #
# Projection
# --------------------------------------------------------------------------- #

class _Index:
    """Cross-references resolved once for the whole request."""

    def __init__(self, request: GenerationRequest):
        self.sources: dict[str, SourceSpec] = {}
        self.runtimes: dict[str, RuntimeSpec] = {}
        self.host_of: dict[str, str] = {}
        self.links_from: dict[str, list[LinkSpec]] = defaultdict(list)
        self.links_to: dict[str, list[LinkSpec]] = defaultdict(list)
        self.consumers_by_record: dict[str, list[RuntimeSpec]] = defaultdict(list)

        for host in request.hosts:
            for rt in host.runtimes:
                self.runtimes[rt.id] = rt
                self.host_of[rt.id] = host.id
                if rt.kind == "ros2":
                    for s in rt.sources:
                        self.sources[s.id] = s
                if rt.kind in {"converter", "verdict_service"}:
                    for rec in rt.input_from:
                        self.consumers_by_record[rec].append(rt)
        for ln in request.links:
            self.links_from[ln.from_runtime].append(ln)
            self.links_to[ln.to_runtime].append(ln)

    def local_consumers(self, record_id: Any, host_id: str, kind: str) -> list[RuntimeSpec]:
        return [
            rt for rt in self.consumers_by_record.get(record_id, [])
            if rt.kind == kind and self.host_of.get(rt.id) == host_id
        ]

    def cross_links(self, links: list[LinkSpec], host_id: str, payload: str) -> list[LinkSpec]:
        return [
            l for l in links
            if l.payload == payload and l.to_host != host_id and l.from_host == host_id
        ]


def _output_dir(host_id: str) -> str:
    return f"./output/{host_id}"


# Shared, link-scoped JSONL location for `file` transports. Both ends of a
# link derive the same path from the link id, so writer and reader always
# agree (a local file same-host, a shared mount cross-host).
_TRANSPORT_DIR = "./output/transport"


def _link_id(link: LinkSpec) -> str:
    return link.id or f"{link.from_runtime}_to_{link.to_runtime}"


def _records_prefix(link: LinkSpec) -> str:
    return link.transport.topic_prefix or "monitor/"


def _file_path(link: LinkSpec) -> str:
    return f"{_TRANSPORT_DIR}/{_link_id(link)}.jsonl"


def _dsl_topic(link: LinkSpec, conv: RuntimeSpec | None) -> str:
    if link.transport.topic:
        return link.transport.topic
    if conv is not None and conv.output_to:
        return f"dsl/{conv.output_to}"
    return f"dsl/{_link_id(link)}"


def _unsupported(link: LinkSpec) -> ValueError:
    return ValueError(
        f"link '{_link_id(link)}': unsupported transport kind "
        f"'{link.transport.kind}' (supported: mqtt, file)."
    )


def _records_exporter(link: LinkSpec) -> dict[str, Any]:
    """Outbound DataRecord transport for a records link."""
    t = link.transport
    if t.kind == "file":
        return {
            "type": "file",
            "output_dir": _TRANSPORT_DIR,
            "session_id": _link_id(link),
            "filename_suffix": "",
        }
    if t.kind == "mqtt":
        return {
            "type": "mqtt",
            "broker": t.broker,
            "port": t.port,
            "topic_prefix": _records_prefix(link),
            "qos": t.qos,
        }
    raise _unsupported(link)


def _records_input(link: LinkSpec) -> dict[str, Any]:
    """Inbound DataRecord endpoint for a records link."""
    if link.transport.kind == "file":
        return {
            "id": _link_id(link),
            "payload": "records",
            "type": "file",
            "path": _file_path(link),
            "follow": True,
        }
    if link.transport.kind == "mqtt":
        t = link.transport
        return {
            "id": _link_id(link),
            "payload": "records",
            "type": "mqtt",
            "broker": t.broker,
            "port": t.port,
            "topic_filter": _records_prefix(link) + "#",
            "qos": t.qos,
        }
    raise _unsupported(link)


def _records_output(link: LinkSpec) -> dict[str, Any]:
    """Outbound DataRecord endpoint for a records link leaving a converter."""
    exporter = _records_exporter(link)
    return {"id": _link_id(link), "payload": "records", **exporter}


def _dsl_output(link: LinkSpec, conv: RuntimeSpec | None) -> dict[str, Any]:
    t = link.transport
    if t.kind == "file":
        return {
            "id": _link_id(link),
            "payload": "dsl",
            "type": "file",
            "path": _file_path(link),
        }
    if t.kind == "mqtt":
        return {
            "id": _link_id(link),
            "payload": "dsl",
            "type": "mqtt",
            "topic": _dsl_topic(link, conv),
            "broker": t.broker,
            "port": t.port,
            "qos": t.qos,
        }
    raise _unsupported(link)


def _dsl_input(link: LinkSpec, conv: RuntimeSpec | None) -> dict[str, Any]:
    t = link.transport
    if t.kind == "file":
        return {
            "id": _link_id(link),
            "payload": "dsl",
            "type": "file",
            "path": _file_path(link),
            "follow": True,
        }
    if t.kind == "mqtt":
        return {
            "id": _link_id(link),
            "payload": "dsl",
            "type": "mqtt",
            "topic": _dsl_topic(link, conv),
            "broker": t.broker,
            "port": t.port,
            "qos": t.qos,
        }
    raise _unsupported(link)


def _outlet_to_exporter(outlet: dict[str, Any]) -> dict[str, Any]:
    e = dict(outlet)
    kind = e.pop("kind", None)
    return {"type": kind, **e}


def _verdict_block(verdict: RuntimeSpec) -> dict[str, Any]:
    block: dict[str, Any] = {"id": verdict.id, "type": verdict.class_path}
    if verdict.params:
        block["params"] = dict(verdict.params)
    outlets = verdict.output_to or [{"kind": "stdout"}]
    block["exporters"] = [_outlet_to_exporter(o) for o in outlets]
    return block


def _converter_entry(conv: RuntimeSpec) -> dict[str, Any]:
    entry: dict[str, Any] = {"id": conv.id, "type": conv.class_path}
    if conv.params:
        entry["params"] = dict(conv.params)
    return entry


class _GraphSection:
    """Accumulates the converters/verdict_services/outputs/links sections of
    one host's YAML."""

    def __init__(self, host: HostSpec, idx: _Index):
        self.host = host
        self.idx = idx
        self.converters: list[dict[str, Any]] = []
        self.verdicts: list[dict[str, Any]] = []
        self.outputs: list[dict[str, Any]] = []
        self.links: list[dict[str, Any]] = []
        self.inputs: list[dict[str, Any]] = []

    def _add_output(self, entry: dict[str, Any]) -> None:
        if not any(o["id"] == entry["id"] for o in self.outputs):
            self.outputs.append(entry)

    def _add_input(self, entry: dict[str, Any]) -> str:
        # Dedupe by transport identity so N same-broker feeds become one input.
        identity = {k: v for k, v in entry.items() if k != "id"}
        for existing in self.inputs:
            if {k: v for k, v in existing.items() if k != "id"} == identity:
                return str(existing["id"])
        self.inputs.append(entry)
        return str(entry["id"])

    def _add_verdict(self, verdict: RuntimeSpec) -> None:
        if not any(v["id"] == verdict.id for v in self.verdicts):
            self.verdicts.append(_verdict_block(verdict))

    def add_converter(self, conv: RuntimeSpec) -> None:
        self.converters.append(_converter_entry(conv))

        for source_id in conv.input_from:
            src = self.idx.sources.get(source_id)
            if src is not None:
                self.links.append({
                    "from": f"source:{src.name}",
                    "to": f"converter:{conv.id}",
                })

        for verdict in self.idx.local_consumers(conv.output_to, self.host.id, "verdict_service"):
            self._add_verdict(verdict)
            self.links.append({
                "from": f"converter:{conv.id}",
                "to": f"verdict:{verdict.id}",
            })
        for downstream in self.idx.local_consumers(conv.output_to, self.host.id, "converter"):
            self.links.append({
                "from": f"converter:{conv.id}",
                "to": f"converter:{downstream.id}",
            })

        for link in self.idx.cross_links(self.idx.links_from.get(conv.id, []), self.host.id, "dsl"):
            self._add_output(_dsl_output(link, conv))
            self.links.append({
                "from": f"converter:{conv.id}",
                "to": f"output:{_link_id(link)}",
            })
        for link in self.idx.cross_links(self.idx.links_from.get(conv.id, []), self.host.id, "records"):
            self._add_output(_records_output(link))
            self.links.append({
                "from": f"converter:{conv.id}",
                "to": f"output:{_link_id(link)}",
            })

    def add_verdict_inputs(self, verdict: RuntimeSpec) -> None:
        self._add_verdict(verdict)
        for link in self.idx.links_to.get(verdict.id, []):
            if link.payload != "dsl" or link.from_host == self.host.id:
                continue
            conv = self.idx.runtimes.get(link.from_runtime)
            input_id = self._add_input(_dsl_input(link, conv))
            self.links.append({
                "from": f"input:{input_id}",
                "to": f"verdict:{verdict.id}",
            })

    def add_converter_inputs(self, conv: RuntimeSpec) -> None:
        for link in self.idx.links_to.get(conv.id, []):
            if link.payload != "records" or link.from_host == self.host.id:
                continue
            self._add_input(_records_input(link))

    def apply(self, config: dict[str, Any]) -> None:
        if self.inputs:
            config["inputs"] = self.inputs
        if self.converters:
            config["converters"] = self.converters
        if self.verdicts:
            config["verdict_services"] = self.verdicts
        if self.outputs:
            config["outputs"] = self.outputs
        if self.links:
            config["links"] = self.links


_KIND_TO_SECTION = {"topic": "topics", "service": "services", "action": "actions"}


def _source_entry(src: SourceSpec, exporters: list[dict[str, Any]]) -> dict[str, Any]:
    entry: dict[str, Any] = {"name": src.name}
    if src.interface:
        entry["type"] = src.interface
    entry["exporters"] = exporters
    return entry


def _build_monitor_host(host: HostSpec, idx: _Index) -> GeneratedConfig:
    monitors = [r for r in host.runtimes if r.kind == "monitor"]
    converters = [r for r in host.runtimes if r.kind == "converter"]
    verdicts = [r for r in host.runtimes if r.kind == "verdict_service"]

    config: dict[str, Any] = {
        "monitor": {"output_dir": _output_dir(host.id), "session_id_prefix": host.id},
    }

    for mon in monitors:
        cross = idx.cross_links(idx.links_from.get(mon.id, []), host.id, "records")
        exporters = [_records_exporter(l) for l in cross]
        deduped: list[dict[str, Any]] = []
        for e in exporters:
            if e not in deduped:
                deduped.append(e)
        if not deduped:
            deduped = [{"type": "file"}]
        for sid in mon.subscribe:
            src = idx.sources.get(sid)
            if src is None:
                continue
            section = _KIND_TO_SECTION.get(src.source_kind, "topics")
            config.setdefault(section, []).append(_source_entry(src, list(deduped)))

    graph = _GraphSection(host, idx)
    for conv in converters:
        for link in idx.links_to.get(conv.id, []):
            if link.payload == "records" and link.from_host != host.id:
                raise ValueError(
                    f"host '{host.id}': converter '{conv.id}' cannot consume a "
                    "cross-host records link on a monitor host; place it on a "
                    "host without a monitor."
                )
        graph.add_converter(conv)
    for verdict in verdicts:
        for link in idx.links_to.get(verdict.id, []):
            if link.payload == "dsl" and link.from_host != host.id:
                raise ValueError(
                    f"host '{host.id}': verdict '{verdict.id}' cannot consume a "
                    "cross-host dsl link on a monitor host; place it on a host "
                    "without a monitor."
                )
        graph._add_verdict(verdict)
    graph.apply(config)

    return GeneratedConfig(host.id, "monitor_node", config)


def _build_runner_host(host: HostSpec, idx: _Index) -> GeneratedConfig:
    converters = [r for r in host.runtimes if r.kind == "converter"]
    verdicts = [r for r in host.runtimes if r.kind == "verdict_service"]

    config: dict[str, Any] = {"monitor": {"output_dir": _output_dir(host.id)}}

    graph = _GraphSection(host, idx)
    for conv in converters:
        graph.add_converter_inputs(conv)
        graph.add_converter(conv)
    for verdict in verdicts:
        graph.add_verdict_inputs(verdict)
    graph.apply(config)

    return GeneratedConfig(host.id, "node_runner", config)


def project(request: GenerationRequest) -> dict[str, GeneratedConfig]:
    """Project a generation request onto runtime YAML, one entry per host that
    runs something. ``ros2``-only hosts produce no file."""
    idx = _Index(request)
    out: dict[str, GeneratedConfig] = {}
    for host in request.hosts:
        kinds = {r.kind for r in host.runtimes}
        if "monitor" in kinds:
            out[host.id] = _build_monitor_host(host, idx)
        elif kinds & {"converter", "verdict_service"}:
            out[host.id] = _build_runner_host(host, idx)
        # ros2-only host: nothing to emit
    return out


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main() -> int:
    import argparse
    import os

    parser = argparse.ArgumentParser(
        description="Project a deployment JSON request into runtime YAML files.",
    )
    parser.add_argument("request", help="Path to the generation-request JSON.")
    parser.add_argument(
        "-o", "--out-dir", default=".",
        help="Directory to write generated <host>.yaml files (default: cwd).",
    )
    args = parser.parse_args()

    request = GenerationRequest.load(args.request)
    generated = project(request)
    os.makedirs(args.out_dir, exist_ok=True)

    for gen in generated.values():
        path = os.path.join(args.out_dir, gen.filename)
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(gen.config, f, sort_keys=False, allow_unicode=True)
        print(f"{path}\n    {gen.run_command().replace('<outdir>', args.out_dir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
