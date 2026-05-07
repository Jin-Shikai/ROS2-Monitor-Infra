"""Helpers for wiring DSL converter chains.

`build_converter_chain` constructs one
    DataConverter -> Dispatcher[Any] -> VerdictExporter (-> FileVerdictSink)
chain from a YAML spec. Used by both the ROS2 monitor side (`MonitorNode`)
and the verdict-side runner (`verdict_runner`). This module is deliberately
free of rclpy imports so it can run on a verdict box without ROS2 installed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from converter import ConverterExporter, resolve_converter_class
from exporter import Dispatcher, FileExporter
from verdict import (
    FileVerdictSink,
    VerdictExporter,
    resolve_verdict_class,
)


def build_converter_chain(
    spec: dict,
    output_dir: str,
    session_id: str,
    logger: Any,
) -> tuple[ConverterExporter, list[FileVerdictSink]] | None:
    """Build one DSL chain from a YAML spec entry.

    Returns the ConverterExporter (to be registered on the raw dispatcher)
    plus any FileVerdictSinks that need closing on shutdown. Returns None
    if the spec is malformed or any class fails to resolve / instantiate.

    The `logger` parameter accepts either an rclpy logger or a stdlib
    `logging.Logger` — only `.info()` and `.error()` are called.
    """
    converter_type = spec.get("type")
    if not converter_type:
        logger.error(f"Converter spec missing 'type'; skipping: {spec}")
        return None

    verdict_spec = spec.get("verdict")
    if not verdict_spec or not verdict_spec.get("type"):
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
    conv_kwargs = {
        k: v for k, v in spec.items() if k not in ("type", "verdict", "output")
    }
    try:
        converter = conv_cls(**conv_kwargs)
    except Exception as ex:
        logger.error(f"Failed to build converter '{converter_type}': {ex}")
        return None

    try:
        v_cls = resolve_verdict_class(verdict_spec["type"])
    except (KeyError, ImportError, AttributeError, TypeError, ValueError) as ex:
        logger.error(f"Cannot resolve verdict service '{verdict_spec['type']}': {ex}")
        return None
    v_kwargs = {
        k: v for k, v in verdict_spec.items() if k not in ("type", "output")
    }
    try:
        verdict_service = v_cls(**v_kwargs)
    except Exception as ex:
        logger.error(f"Failed to build verdict service: {ex}")
        return None

    sinks: list[FileVerdictSink] = []
    sink = None
    verdict_output = verdict_spec.get("output")
    if verdict_output:
        out_path = Path(verdict_output)
        if not out_path.is_absolute():
            out_path = Path(output_dir) / verdict_output
        out_path = Path(str(out_path).replace("{session_id}", session_id))
        sink_obj = FileVerdictSink(str(out_path))
        sinks.append(sink_obj)
        sink = sink_obj

    dsl_dispatcher: Dispatcher = Dispatcher(label=f"DSL[{converter_type}]")
    dsl_dispatcher.add(VerdictExporter(verdict_service, sink=sink))

    # Optional: also archive dsl records to a file for offline replay.
    dsl_record_output = spec.get("output")
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

    logger.info(
        f"Converter chain enabled: {converter_type} -> {verdict_spec['type']}"
    )
    return ConverterExporter(converter, dsl_dispatcher), sinks
