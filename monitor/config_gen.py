"""Generation-request layer: project a deployment JSON into runtime YAML.

This is the *generation* layer described in `Thesis/Pseudocode/pseudocode.tex`.
A request is a deployment model — physical ``hosts`` own executable
``runtimes`` (``ros2`` / ``monitor`` / ``converter`` / ``verdict_service``),
and ``links`` describe how hosts exchange records / dsl records / verdicts.

The module does *not* re-implement the runtime. It only **projects** the
request onto the existing runtime YAML that `config_model.MonitorConfig` /
`RunnerConfig` already parse, so `monitor_node`, `verdict_runner` and
`split_runner` keep consuming exactly what they consume today:

    GenerationRequest --project()--> { host_id: GeneratedConfig(runtime YAML) }

Concepts are normalised onto the UML class diagram:

  * a ``Transformer`` is gone — it is a ``Converter`` whose ``converter`` kind
    is ``data_filter`` (record->record work: rate control, aggregation, ...);
    a ``dsl_converter`` is the record->dsl kind. Both are plain converter
    plugins addressed by ``class_path`` and both pair with a verdict service.
  * ``output_to`` is the single outlet concept. A converter's ``output_to`` is
    a record id (relay to the next stage); a verdict service's ``output_to`` is
    a list of outlets ``[{"kind": "stdout|file|mqtt", ...}]``. There is no
    separate "sink" concept — a ``Link.transport`` outlet and an ``output_to``
    outlet mean the same thing: where records/relays go.

Projection rules (one YAML per host, entrypoint chosen by the host's runtimes):

  * host with a ``monitor``         -> ``monitor_node`` YAML (topics + optional
    in-process converters when converter/verdict are co-located).
  * host with a ``converter`` whose paired verdict is on another host
                                    -> ``split_runner --role converter`` YAML.
  * host with a ``verdict_service`` fed by a cross-host ``dsl`` link
                                    -> ``split_runner --role verdict`` YAML.
  * host with co-located converter+verdict but no monitor
                                    -> ``verdict_runner`` YAML.
  * ``ros2``-only host              -> no file (it only supplies sources).
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import yaml


# --------------------------------------------------------------------------- #
# Request-layer model (mirrors the UML class diagram)
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class TransportSpec:
    """A ``Link.transport`` outlet. ``kind`` selects the carrier; the rest are
    connection details the request may pin (broker/port/qos) and an optional
    explicit ``topic`` (otherwise derived)."""

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
    converter: str | None = None          # "data_filter" | "dsl_converter"
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
    payload: str                          # "records" | "dsl" | "verdicts"
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
    entrypoint: str                # "monitor_node" | "verdict_runner" | "split_runner"
    role: str | None               # "converter" | "verdict" for split_runner, else None
    config: dict[str, Any]

    @property
    def filename(self) -> str:
        return f"{self.host_id}.yaml"

    def run_command(self) -> str:
        cfg = f"<outdir>/{self.filename}"
        if self.entrypoint == "monitor_node":
            return f"python monitor/monitor_node.py -c {cfg}"
        if self.entrypoint == "verdict_runner":
            return f"python monitor/verdict_runner.py -c {cfg}"
        return f"python monitor/split_runner.py --role {self.role} -c {cfg}"


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
        self.verdict_by_record: dict[str, RuntimeSpec] = {}

        for host in request.hosts:
            for rt in host.runtimes:
                self.runtimes[rt.id] = rt
                self.host_of[rt.id] = host.id
                if rt.kind == "ros2":
                    for s in rt.sources:
                        self.sources[s.id] = s
                if rt.kind == "verdict_service":
                    for rec in rt.input_from:
                        self.verdict_by_record[rec] = rt
        for ln in request.links:
            self.links_from[ln.from_runtime].append(ln)
            self.links_to[ln.to_runtime].append(ln)

    def first_link(self, links: list[LinkSpec], payload: str) -> LinkSpec | None:
        return next((l for l in links if l.payload == payload), None)


def _output_dir(host_id: str) -> str:
    return f"./output/{host_id}"


def _outlet_to_exporter(outlet: dict[str, Any]) -> dict[str, Any]:
    """An ``output_to`` outlet (``{"kind": ..., ...}``) is the same idea as a
    runtime exporter (``{"type": ..., ...}``)."""
    e = dict(outlet)
    kind = e.pop("kind", None)
    return {"type": kind, **e}


def _verdict_block(verdict: RuntimeSpec) -> dict[str, Any]:
    block: dict[str, Any] = {"type": verdict.class_path}
    block.update(verdict.params)
    outlets = verdict.output_to or [{"kind": "stdout"}]
    block["exporters"] = [_outlet_to_exporter(o) for o in outlets]
    return block


def _resolve_inputs(input_from: list[str], idx: _Index) -> list[str]:
    """Map converter ``input_from`` source-ids onto the ``DataRecord.source_name``
    values the runtime ``inputs:`` filter matches. Ids that name a record (not a
    ros2 source) carry no source-name filter and are dropped here."""
    names = [idx.sources[i].name for i in input_from if i in idx.sources]
    return names


def _converter_entry(conv: RuntimeSpec, idx: _Index) -> dict[str, Any]:
    entry: dict[str, Any] = {"type": conv.class_path}
    entry.update(conv.params)
    inputs = _resolve_inputs(conv.input_from, idx)
    if inputs:
        entry["inputs"] = inputs
    return entry


def _dsl_topic(link: LinkSpec, conv: RuntimeSpec) -> str:
    if link.transport.topic:
        return link.transport.topic
    return f"dsl/{conv.output_to}"


def _dsl_transport_block(link: LinkSpec, conv: RuntimeSpec) -> dict[str, Any]:
    t = link.transport
    if t.kind != "mqtt":
        raise ValueError(
            f"dsl link '{link.id}': transport kind '{t.kind}' is not supported "
            f"(split_runner's DSL transport is MQTT-only). Use kind 'mqtt', or "
            f"co-locate the converter and verdict on one host for an in-process "
            f"chain (no transport)."
        )
    return {
        "topic": _dsl_topic(link, conv),
        "broker": t.broker,
        "port": t.port,
        "qos": t.qos,
    }


# Shared, link-scoped JSONL location for `file` record transports. Both ends of
# a link derive the same path from the link id, so writer and reader always
# agree (a local file same-host, a shared mount cross-host).
_TRANSPORT_DIR = "./output/transport"


def _records_prefix(link: LinkSpec) -> str:
    """The MQTT namespace for a records link. Both ends derive it from the same
    link, so the exporter prefix and the source filter always agree."""
    return link.transport.topic_prefix or "monitor/"


def _records_file_path(link: LinkSpec) -> str:
    return f"{_TRANSPORT_DIR}/{link.id}.jsonl"


def _records_source(link: LinkSpec) -> dict[str, Any]:
    """Inbound DataRecord transport for a records link, per transport kind."""
    t = link.transport
    if t.kind == "file":
        return {"type": "file", "path": _records_file_path(link)}
    if t.kind == "mqtt":
        return {
            "type": "mqtt",
            "broker": t.broker,
            "port": t.port,
            "topic_filter": _records_prefix(link) + "#",
            "qos": t.qos,
        }
    raise ValueError(
        f"records link '{link.id}': unsupported transport kind '{t.kind}' "
        f"(supported: mqtt, file)."
    )


def _records_exporter(link: LinkSpec) -> dict[str, Any]:
    """Outbound DataRecord transport for a records link, per transport kind."""
    t = link.transport
    if t.kind == "file":
        # explicit session_id + empty suffix => deterministic, shared filename
        # (the framework only fills these when omitted).
        return {
            "type": "file",
            "output_dir": _TRANSPORT_DIR,
            "session_id": link.id,
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
    raise ValueError(
        f"records link '{link.id}': unsupported transport kind '{t.kind}' "
        f"(supported: mqtt, file)."
    )


def _record_transport_block(link: LinkSpec) -> dict[str, Any]:
    """A filter's output: republish DataRecords on this link, per transport kind.
    Carries `kind` so `split_runner --role filter` picks file vs mqtt."""
    t = link.transport
    if t.kind == "file":
        return {
            "kind": "file",
            "output_dir": _TRANSPORT_DIR,
            "session_id": link.id,
        }
    if t.kind == "mqtt":
        return {
            "kind": "mqtt",
            "topic_prefix": _records_prefix(link),
            "broker": t.broker,
            "port": t.port,
            "qos": t.qos,
        }
    raise ValueError(
        f"records link '{link.id}': unsupported transport kind '{t.kind}' "
        f"(supported: mqtt, file)."
    )


def _source_entry(src: SourceSpec, exporter: dict[str, Any]) -> dict[str, Any]:
    entry: dict[str, Any] = {"name": src.name}
    if src.interface:
        entry["type"] = src.interface
    entry["exporters"] = [exporter]
    return entry


_KIND_TO_SECTION = {"topic": "topics", "service": "services", "action": "actions"}


def _build_monitor_host(host: HostSpec, idx: _Index) -> GeneratedConfig:
    monitors = [r for r in host.runtimes if r.kind == "monitor"]
    converters = [r for r in host.runtimes if r.kind == "converter"]

    config: dict[str, Any] = {
        "monitor": {"output_dir": _output_dir(host.id), "session_id_prefix": host.id},
    }

    for mon in monitors:
        records_link = idx.first_link(idx.links_from.get(mon.id, []), "records")
        # cross-host monitor -> the link's transport; same-host (or no link) ->
        # archive locally to file and let the converter read records in-process.
        if records_link is not None and records_link.to_host != host.id:
            exporter = _records_exporter(records_link)
        else:
            exporter = {"type": "file"}
        for sid in mon.subscribe:
            src = idx.sources.get(sid)
            if src is None:
                continue
            section = _KIND_TO_SECTION.get(src.source_kind, "topics")
            config.setdefault(section, []).append(_source_entry(src, exporter))

    # co-located converter+verdict run in-process inside monitor_node
    chain_entries: list[dict[str, Any]] = []
    for conv in converters:
        verdict = idx.verdict_by_record.get(conv.output_to)
        if verdict is None or idx.host_of.get(verdict.id) != host.id:
            continue
        entry = _converter_entry(conv, idx)
        entry["verdict"] = _verdict_block(verdict)
        chain_entries.append(entry)
    if chain_entries:
        config["converters"] = chain_entries

    return GeneratedConfig(host.id, "monitor_node", None, config)


def _build_converter_host(host: HostSpec, idx: _Index) -> GeneratedConfig:
    converters = [r for r in host.runtimes if r.kind == "converter"]

    config: dict[str, Any] = {"monitor": {"output_dir": _output_dir(host.id)}}

    # inbound DataRecords come from the records link feeding any converter here
    records_link = None
    for conv in converters:
        records_link = idx.first_link(idx.links_to.get(conv.id, []), "records")
        if records_link is not None:
            break
    if records_link is not None:
        config["verdict_runner"] = {"source": _records_source(records_link)}

    entries: list[dict[str, Any]] = []
    role: str | None = None
    for conv in converters:
        entry = _converter_entry(conv, idx)
        verdict = idx.verdict_by_record.get(conv.output_to)
        dsl_link = idx.first_link(idx.links_from.get(conv.id, []), "dsl")
        records_out = idx.first_link(idx.links_from.get(conv.id, []), "records")
        if verdict is not None and idx.host_of.get(verdict.id) == host.id:
            # co-located: full in-process chain for verdict_runner
            entry["verdict"] = _verdict_block(verdict)
        elif dsl_link is not None:
            # cross-host dsl_converter: publish DSL records to the verdict half
            entry["dsl_transport"] = _dsl_transport_block(dsl_link, conv)
            role = "converter"
        elif records_out is not None:
            # cross-host data_filter: republish DataRecords to the next converter
            entry["record_transport"] = _record_transport_block(records_out)
            role = "filter"
        entries.append(entry)
    config["converters"] = entries

    if role is not None:
        return GeneratedConfig(host.id, "split_runner", role, config)
    return GeneratedConfig(host.id, "verdict_runner", None, config)


def _build_verdict_host(host: HostSpec, idx: _Index) -> GeneratedConfig:
    verdicts = [r for r in host.runtimes if r.kind == "verdict_service"]

    config: dict[str, Any] = {"monitor": {"output_dir": _output_dir(host.id)}}
    entries: list[dict[str, Any]] = []
    for verdict in verdicts:
        dsl_link = idx.first_link(idx.links_to.get(verdict.id, []), "dsl")
        if dsl_link is None:
            continue
        conv = idx.runtimes.get(dsl_link.from_runtime)
        entry: dict[str, Any] = {
            # the converter type is only a label on the verdict side; the seam
            # is the shared dsl_transport topic.
            "type": conv.class_path if conv else "converter",
            "dsl_transport": _dsl_transport_block(dsl_link, conv) if conv else {},
            "verdict": _verdict_block(verdict),
        }
        entries.append(entry)
    config["converters"] = entries

    return GeneratedConfig(host.id, "split_runner", "verdict", config)


def project(request: GenerationRequest) -> dict[str, GeneratedConfig]:
    """Project a generation request onto runtime YAML, one entry per host that
    runs something. ``ros2``-only hosts produce no file."""
    idx = _Index(request)
    out: dict[str, GeneratedConfig] = {}
    for host in request.hosts:
        kinds = {r.kind for r in host.runtimes}
        if "monitor" in kinds:
            out[host.id] = _build_monitor_host(host, idx)
        elif "converter" in kinds:
            out[host.id] = _build_converter_host(host, idx)
        elif "verdict_service" in kinds:
            out[host.id] = _build_verdict_host(host, idx)
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
