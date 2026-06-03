"""Helpers for wiring DSL converter chains.

`build_converter_chain` constructs one

    DataConverter -> Dispatcher[Any] -> VerdictExporter -> Dispatcher[Verdict] -> Exporter[Verdict]+

chain from a YAML spec. Used by both the ROS2 monitor side (`MonitorNode`)
and the verdict-side runner (`verdict_runner`). This module is deliberately
free of rclpy imports so it can run on a verdict box without ROS2 installed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from config_model import ConverterSpec, VerdictSpec
from converter import ConverterExporter, resolve_converter_class
from data_record import DataRecord
from exporter import Dispatcher, Exporter, FileExporter
from verdict import VerdictExporter, resolve_verdict_class
from verdict_exporters import resolve_verdict_exporter_class


class _SourceFilteredExporter(Exporter):
    """Wraps an inner Exporter and only forwards records whose
    `source_name` is in the allowed set. Used to implement the
    `converters: - inputs: [...]` YAML filter — keeps the source-
    selection concern out of every custom converter.
    """

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


def _substitute_session_id(value: Any, session_id: str) -> Any:
    """Replace `{session_id}` in any string kwarg, recursively for dict/list."""
    if isinstance(value, str):
        return value.replace("{session_id}", session_id)
    if isinstance(value, dict):
        return {k: _substitute_session_id(v, session_id) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_session_id(v, session_id) for v in value]
    return value


def _build_verdict_dispatcher(
    verdict_spec: VerdictSpec,
    output_dir: str,
    session_id: str,
    converter_type: str,
    logger: Any,
) -> Dispatcher | None:
    """Build the Dispatcher[Verdict] from `verdict.exporters: [...]`.
    Returns None if any exporter fails to resolve / instantiate —
    caller logs and skips the chain.
    """
    specs = verdict_spec.exporters
    dispatcher: Dispatcher = Dispatcher(label=f"Verdict[{converter_type}]")
    for spec in specs:
        if not spec.type:
            logger.error(f"Verdict exporter spec missing 'type'; skipping entry: {spec.raw}")
            return None
        try:
            cls = resolve_verdict_exporter_class(spec.type)
        except (KeyError, ImportError, AttributeError, TypeError, ValueError) as ex:
            logger.error(f"Cannot resolve verdict exporter '{spec.type}': {ex}")
            return None
        kwargs = dict(spec.kwargs)
        kwargs = _substitute_session_id(kwargs, session_id)
        # file paths that are relative resolve against output_dir
        if "path" in kwargs and isinstance(kwargs["path"], str):
            p = Path(kwargs["path"])
            if not p.is_absolute():
                p = Path(output_dir) / p
            kwargs["path"] = str(p)
        try:
            dispatcher.add(cls(**kwargs))
        except Exception as ex:
            logger.error(f"Failed to build verdict exporter '{spec.type}': {ex}")
            return None
    return dispatcher


def build_converter_chain(
    spec: ConverterSpec,
    output_dir: str,
    session_id: str,
    logger: Any,
) -> tuple[Exporter, Dispatcher] | None:
    """Build one DSL chain from a YAML spec entry.

    Returns the `ConverterExporter` (to be registered on the raw
    DataRecord dispatcher) plus the `Dispatcher[Verdict]` carrying the
    chain's verdict exporters — caller closes it on shutdown. Returns
    None if the spec is malformed or any class fails to resolve.

    The `logger` parameter accepts either an rclpy logger or a stdlib
    `logging.Logger` — only `.info()` and `.error()` are called.
    """
    converter_type = spec.type
    if not converter_type:
        logger.error(f"Converter spec missing 'type'; skipping: {spec.raw}")
        return None

    verdict_spec = spec.verdict
    if verdict_spec is None or not verdict_spec.type:
        logger.error(
            f"Converter '{converter_type}' must include a 'verdict' "
            f"section with a 'type'; skipping."
        )
        return None

    try:
        conv_cls = resolve_converter_class(converter_type)
    except (KeyError, ImportError, AttributeError, TypeError, ValueError) as ex:
        logger.error(f"Cannot resolve converter '{converter_type}': {ex}")
        return None
    try:
        converter = conv_cls(**spec.kwargs)
    except Exception as ex:
        logger.error(f"Failed to build converter '{converter_type}': {ex}")
        return None

    try:
        v_cls = resolve_verdict_class(verdict_spec.type)
    except (KeyError, ImportError, AttributeError, TypeError, ValueError) as ex:
        logger.error(f"Cannot resolve verdict service '{verdict_spec.type}': {ex}")
        return None
    try:
        verdict_service = v_cls(**verdict_spec.kwargs)
    except Exception as ex:
        logger.error(f"Failed to build verdict service: {ex}")
        return None

    verdict_dispatcher = _build_verdict_dispatcher(
        verdict_spec, output_dir, session_id, converter_type, logger,
    )
    if verdict_dispatcher is None:
        return None

    # When no exporters are configured at all, fall back to VerdictExporter's
    # default (stdout). Otherwise hand the Dispatcher[Verdict] directly —
    # Dispatcher is itself an Exporter[Verdict], so VerdictExporter just calls
    # `.export()` on it and fan-out happens inside the dispatcher.
    downstream = verdict_dispatcher if not verdict_dispatcher.is_empty() else None

    dsl_dispatcher: Dispatcher = Dispatcher(label=f"DSL[{converter_type}]")
    dsl_dispatcher.add(VerdictExporter(verdict_service, exporter=downstream))

    # Optional: also archive dsl records to a file for offline replay.
    dsl_record_output = spec.output
    if dsl_record_output:
        out_path = Path(dsl_record_output)
        if not out_path.is_absolute():
            out_path = Path(output_dir) / dsl_record_output
        out_path = Path(str(out_path).replace("{session_id}", session_id))
        dsl_dispatcher.add(
            FileExporter(
                output_dir=str(out_path.parent),
                session_id=out_path.stem,
                filename_suffix="",
            )
        )

    inputs = spec.inputs
    if inputs is not None:
        if not isinstance(inputs, list) or not all(isinstance(s, str) for s in inputs):
            logger.error(
                f"Converter '{converter_type}' has invalid 'inputs' "
                f"(must be a list of source-name strings); skipping."
            )
            return None
        if not inputs:
            logger.error(
                f"Converter '{converter_type}' has empty 'inputs' list "
                f"(would match nothing); skipping."
            )
            return None
        outer: Exporter = _SourceFilteredExporter(
            ConverterExporter(converter, dsl_dispatcher),
            allowed_sources=set(inputs),
        )
        input_note = f" inputs={inputs}"
    else:
        outer = ConverterExporter(converter, dsl_dispatcher)
        input_note = " inputs=<all>"

    logger.info(
        f"Converter chain enabled: {converter_type} -> {verdict_spec.type}"
        f"{input_note} ({verdict_dispatcher.size} verdict exporter(s))"
    )
    return outer, verdict_dispatcher
