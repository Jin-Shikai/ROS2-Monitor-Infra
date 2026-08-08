"""Graph wiring for converter / verdict / transport-endpoint nodes.

`build_graph` turns the declarative node graph of a runtime YAML into live
wiring. This module is deliberately free of rclpy imports so it can run on
hosts without ROS2 installed.

Node kinds referenced by `links:`:

    source:<DataRecord.source_name>   record-stream filter for a converter
    input:<inputs id>                 inbound dsl endpoint (routed by links)
    converter:<converters id>         DataConverter node
    verdict:<verdict_services id>     VerdictService node
    output:<outputs id>               outbound transport endpoint

Supported edges:

    source:*    -> converter:*        select which records a converter sees
    input:*     -> verdict:*          feed a verdict from an inbound dsl feed
    input:*     -> output:*           relay/archive an inbound dsl feed
    converter:* -> converter:*        in-process filter chaining
    converter:* -> verdict:*          in-process evaluation
    converter:* -> output:*           publish converter output on a transport

Records inputs are not link targets: every records feed fans into the shared
`record_entry` dispatcher and converters select from it by source name.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from config_model import ConverterSpec, EndpointSpec, RuntimeLinkSpec, VerdictSpec
from converter import ConverterExporter, resolve_converter_class
from data_record import DataRecord
from dsl_transport import resolve_dsl_exporter_class
from exporter import Dispatcher, Exporter
from exporters import resolve_data_record_exporter_class
from verdict import VerdictExporter, resolve_verdict_class
from verdict_exporters import resolve_verdict_exporter_class


class _SourceFilteredExporter(Exporter):
    """Wraps an inner Exporter and only forwards DataRecords whose
    `source_name` is in the allowed set."""

    def __init__(self, inner: Exporter, allowed_sources: set[str]):
        self._inner = inner
        self._allowed = set(allowed_sources)

    def export(self, record) -> None:
        if isinstance(record, DataRecord) and record.source_name not in self._allowed:
            return
        self._inner.export(record)

    def flush(self) -> None:
        self._inner.flush()

    def close(self) -> None:
        self._inner.close()


class _Sink(Exporter):
    """Forward into a shared exporter/dispatcher without owning its shutdown."""

    def __init__(self, target: Exporter):
        self._target = target

    def export(self, record) -> None:
        self._target.export(record)

    def flush(self) -> None:
        if isinstance(self._target, Dispatcher):
            self._target.flush_all()
        else:
            self._target.flush()


class _ChainedOnly(Exporter):
    """Holds a chained-only converter for lifecycle purposes without feeding
    it records from the shared stream."""

    def __init__(self, inner: Exporter):
        self._inner = inner

    def export(self, record) -> None:
        return

    def flush(self) -> None:
        self._inner.flush()

    def close(self) -> None:
        self._inner.close()


def _substitute_session_id(value: Any, session_id: str) -> Any:
    """Replace `{session_id}` in any string kwarg, recursively for dict/list."""
    if isinstance(value, str):
        return value.replace("{session_id}", session_id)
    if isinstance(value, dict):
        return {k: _substitute_session_id(v, session_id) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_session_id(v, session_id) for v in value]
    return value


def _resolve_path(kwargs: dict[str, Any], key: str, output_dir: str) -> None:
    value = kwargs.get(key)
    if isinstance(value, str) and value and not Path(value).is_absolute():
        kwargs[key] = str(Path(output_dir) / value)


def _node_ref(value: str) -> tuple[str, str]:
    if ":" not in value:
        return "", value
    kind, ident = value.split(":", 1)
    return kind, ident


def _converter_id(spec: ConverterSpec, index: int) -> str:
    return spec.id or spec.type or f"converter_{index}"


def _verdict_id(spec: VerdictSpec, index: int) -> str:
    return spec.id or spec.type or f"verdict_{index}"


def _build_verdict_dispatcher(
    verdict_spec: VerdictSpec,
    output_dir: str,
    session_id: str,
    label: str,
    logger: Any,
) -> Dispatcher | None:
    """Build the Dispatcher[Verdict] from `exporters: [...]`. Returns None if
    any exporter fails to resolve / instantiate."""
    dispatcher: Dispatcher = Dispatcher(label=f"Verdict[{label}]")
    for spec in verdict_spec.exporters:
        if not spec.type:
            logger.error(f"Verdict exporter spec missing 'type'; skipping entry: {spec.raw}")
            return None
        try:
            cls = resolve_verdict_exporter_class(spec.type)
        except (KeyError, ImportError, AttributeError, TypeError, ValueError) as ex:
            logger.error(f"Cannot resolve verdict exporter '{spec.type}': {ex}")
            return None
        kwargs = _substitute_session_id(dict(spec.kwargs), session_id)
        _resolve_path(kwargs, "path", output_dir)
        try:
            dispatcher.add(cls(**kwargs))
        except Exception as ex:
            logger.error(f"Failed to build verdict exporter '{spec.type}': {ex}")
            return None
    return dispatcher


def build_verdict_stage(
    spec: VerdictSpec,
    output_dir: str,
    session_id: str,
    logger: Any,
) -> tuple[Dispatcher, Dispatcher] | None:
    """Build one verdict node.

    Returns `(dsl_dispatcher, verdict_dispatcher)`:
      * `dsl_dispatcher` — consumes DSL-ready records and runs the
        `VerdictExporter`. Feed it from converters or from a dsl input.
      * `verdict_dispatcher` — the `Dispatcher[Verdict]` of this node's
        verdict exporters; caller closes it on shutdown.
    """
    label = spec.id or spec.type or "?"
    if not spec.type:
        logger.error(f"Verdict service '{label}' missing 'type'; skipping.")
        return None

    try:
        v_cls = resolve_verdict_class(spec.type)
    except (KeyError, ImportError, AttributeError, TypeError, ValueError) as ex:
        logger.error(f"Cannot resolve verdict service '{spec.type}': {ex}")
        return None
    try:
        verdict_service = v_cls(**spec.kwargs)
    except Exception as ex:
        logger.error(f"Failed to build verdict service '{label}': {ex}")
        return None

    verdict_dispatcher = _build_verdict_dispatcher(
        spec, output_dir, session_id, label, logger
    )
    if verdict_dispatcher is None:
        return None

    # No configured exporters -> VerdictExporter's stdout default.
    downstream = verdict_dispatcher if not verdict_dispatcher.is_empty() else None
    dsl_dispatcher: Dispatcher = Dispatcher(label=f"DSL[{label}]")
    dsl_dispatcher.add(VerdictExporter(verdict_service, exporter=downstream))

    logger.info(
        f"Verdict node '{label}': {spec.type} "
        f"({verdict_dispatcher.size} verdict exporter(s))"
    )
    return dsl_dispatcher, verdict_dispatcher


def _build_output_exporter(
    spec: EndpointSpec,
    output_dir: str,
    session_id: str,
    logger: Any,
) -> Exporter | None:
    kwargs = _substitute_session_id(dict(spec.kwargs), session_id)
    type_str = spec.type or ("mqtt" if spec.payload == "dsl" else "file")
    try:
        if spec.payload == "dsl":
            _resolve_path(kwargs, "path", output_dir)
            cls = resolve_dsl_exporter_class(type_str)
        elif spec.payload == "records":
            if type_str == "file":
                kwargs.setdefault("output_dir", output_dir)
                kwargs.setdefault("session_id", session_id)
                kwargs.setdefault("filename_suffix", "")
            cls = resolve_data_record_exporter_class(type_str)
        else:
            logger.error(
                f"Output '{spec.id}' has unsupported payload '{spec.payload}' "
                f"(supported: records, dsl); skipping."
            )
            return None
        return cls(**kwargs)
    except Exception as ex:
        logger.error(f"Failed to build output '{spec.id}' ({type_str}): {ex}")
        return None


def _build_order(
    converter_ids: list[str],
    conv_edges: dict[str, list[str]],
    logger: Any,
) -> list[str] | None:
    """Downstream-first build order over converter->converter edges.
    Returns None on a cycle."""
    pending = set(converter_ids)
    order: list[str] = []
    while pending:
        ready = [
            cid for cid in converter_ids
            if cid in pending
            and all(t not in pending for t in conv_edges.get(cid, []))
        ]
        if not ready:
            logger.error(
                f"Converter links form a cycle among {sorted(pending)}; "
                "graph not built."
            )
            return None
        for cid in ready:
            pending.discard(cid)
            order.append(cid)
    return order


@dataclass
class GraphRuntime:
    """Live wiring built from a runtime graph.

    Feed DataRecords into `record_entry` (collectors, records inputs) and DSL
    records into `input_entries[<inputs id>]` (dsl inputs). Call `close()`
    once on shutdown.
    """

    record_entry: Dispatcher
    input_entries: dict[str, Dispatcher] = field(default_factory=dict)
    converter_count: int = 0
    _dsl_dispatchers: list[Dispatcher] = field(default_factory=list)
    _verdict_dispatchers: list[Dispatcher] = field(default_factory=list)
    _output_exporters: list[Exporter] = field(default_factory=list)

    def close(self) -> None:
        self.record_entry.close_all()
        for dispatcher in self.input_entries.values():
            dispatcher.close_all()
        for dispatcher in self._dsl_dispatchers:
            dispatcher.close_all()
        for dispatcher in self._verdict_dispatchers:
            dispatcher.close_all()
        for exporter in self._output_exporters:
            try:
                exporter.close()
            except Exception:
                pass


def build_graph(
    converters: list[ConverterSpec],
    verdict_services: list[VerdictSpec],
    links: list[RuntimeLinkSpec],
    outputs: list[EndpointSpec],
    output_dir: str,
    session_id: str,
    logger: Any,
) -> GraphRuntime | None:
    """Build the full converter/verdict/output graph of one runtime.

    Returns None when nothing usable was built (no converter and no routed
    verdict/output target).
    """
    converter_by_id = {
        _converter_id(spec, index): spec
        for index, spec in enumerate(converters, start=1)
    }
    verdict_by_id = {
        _verdict_id(spec, index): spec
        for index, spec in enumerate(verdict_services, start=1)
    }
    output_by_id = {spec.id: spec for spec in outputs}

    source_inputs: dict[str, set[str]] = {cid: set() for cid in converter_by_id}
    conv_targets: dict[str, list[tuple[str, str]]] = {cid: [] for cid in converter_by_id}
    input_targets: dict[str, list[tuple[str, str]]] = {}

    for link in links:
        from_kind, from_id = _node_ref(link.from_ref)
        to_kind, to_id = _node_ref(link.to_ref)
        if from_kind == "source" and to_kind == "converter":
            if to_id in source_inputs:
                source_inputs[to_id].add(from_id)
            else:
                logger.warning(f"Link '{link.from_ref} -> {link.to_ref}': unknown converter.")
        elif from_kind == "converter":
            if from_id not in conv_targets:
                logger.warning(f"Link '{link.from_ref} -> {link.to_ref}': unknown converter.")
            elif to_kind in {"converter", "verdict", "output"}:
                conv_targets[from_id].append((to_kind, to_id))
            else:
                logger.warning(f"Link '{link.from_ref} -> {link.to_ref}': unsupported target.")
        elif from_kind == "input" and to_kind in {"verdict", "output"}:
            input_targets.setdefault(from_id, []).append((to_kind, to_id))
        else:
            logger.warning(f"Link '{link.from_ref} -> {link.to_ref}': unsupported edge.")

    # Verdict nodes (instantiated once each, shared across feeders).
    verdict_dsl: dict[str, Dispatcher] = {}
    dsl_dispatchers: list[Dispatcher] = []
    verdict_dispatchers: list[Dispatcher] = []
    for vid, vspec in verdict_by_id.items():
        stage = build_verdict_stage(vspec, output_dir, session_id, logger)
        if stage is None:
            continue
        dsl_dispatcher, verdict_dispatcher = stage
        verdict_dsl[vid] = dsl_dispatcher
        dsl_dispatchers.append(dsl_dispatcher)
        verdict_dispatchers.append(verdict_dispatcher)

    # Output endpoints (one shared exporter instance per id).
    output_exporters: dict[str, Exporter] = {}
    for oid, ospec in output_by_id.items():
        exporter = _build_output_exporter(ospec, output_dir, session_id, logger)
        if exporter is not None:
            output_exporters[oid] = exporter
            logger.info(f"Output '{oid}': {ospec.payload} via {ospec.type or 'default'}")

    conv_edges = {
        cid: [tid for kind, tid in targets if kind == "converter"]
        for cid, targets in conv_targets.items()
    }
    order = _build_order(list(converter_by_id), conv_edges, logger)
    if order is None:
        for d in [*dsl_dispatchers, *verdict_dispatchers]:
            d.close_all()
        for e in output_exporters.values():
            e.close()
        return None

    # Converter nodes, downstream-first so chained targets already exist.
    built: dict[str, Exporter] = {}
    chained_only: set[str] = {
        tid for targets in conv_targets.values()
        for kind, tid in targets if kind == "converter"
    }
    for cid in order:
        spec = converter_by_id[cid]
        if not spec.type:
            logger.error(f"Converter '{cid}' missing 'type'; skipping.")
            continue
        try:
            conv_cls = resolve_converter_class(spec.type)
            converter = conv_cls(**spec.kwargs)
        except Exception as ex:
            logger.error(f"Cannot build converter '{cid}' ({spec.type}): {ex}")
            continue

        downstream: Dispatcher = Dispatcher(label=f"GraphOut[{cid}]")
        for kind, tid in conv_targets.get(cid, []):
            target: Exporter | None
            if kind == "verdict":
                target = verdict_dsl.get(tid)
            elif kind == "converter":
                target = built.get(tid)
            else:
                target = output_exporters.get(tid)
            if target is None:
                logger.warning(f"Converter '{cid}': target {kind}:{tid} unavailable.")
                continue
            downstream.add(_Sink(target))
        if downstream.is_empty():
            logger.warning(f"Converter '{cid}' has no live target; skipping.")
            continue

        inputs = sorted(source_inputs.get(cid, set())) or spec.inputs
        if inputs is not None and (
            not isinstance(inputs, list)
            or not inputs
            or not all(isinstance(s, str) for s in inputs)
        ):
            logger.error(f"Converter '{cid}' has invalid 'inputs'; skipping.")
            continue
        outer: Exporter = ConverterExporter(converter, downstream, label=cid)
        if inputs:
            outer = _SourceFilteredExporter(outer, allowed_sources=set(inputs))
        built[cid] = outer
        logger.info(f"Converter node '{cid}': {spec.type} inputs={inputs or '<all>'}")

    record_entry: Dispatcher = Dispatcher(label="Records")
    for cid, outer in built.items():
        # A chained-only converter (fed by an upstream converter, no source
        # selection of its own) does not read the shared record stream, but
        # its lifecycle is still owned by record_entry.
        feeds_from_records = (
            cid not in chained_only
            or bool(source_inputs.get(cid))
            or converter_by_id[cid].inputs is not None
        )
        record_entry.add(outer if feeds_from_records else _ChainedOnly(outer))

    input_entries: dict[str, Dispatcher] = {}
    for input_id, targets in input_targets.items():
        entry: Dispatcher = Dispatcher(label=f"Input[{input_id}]")
        for kind, tid in targets:
            target = verdict_dsl.get(tid) if kind == "verdict" else output_exporters.get(tid)
            if target is None:
                logger.warning(f"Input '{input_id}': target {kind}:{tid} unavailable.")
                continue
            entry.add(_Sink(target))
        input_entries[input_id] = entry

    if not built and not input_entries:
        for d in [*dsl_dispatchers, *verdict_dispatchers]:
            d.close_all()
        for e in output_exporters.values():
            e.close()
        return None

    return GraphRuntime(
        record_entry=record_entry,
        input_entries=input_entries,
        converter_count=len(built),
        _dsl_dispatchers=dsl_dispatchers,
        _verdict_dispatchers=verdict_dispatchers,
        _output_exporters=list(output_exporters.values()),
    )
