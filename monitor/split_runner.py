"""Split-deployment runner — run the converter stage and the verdict stage on
*separate* hosts, joined by an MQTT DSL-record transport.

This is the runner that exercises the converter/verdict split that the
in-process `verdict_runner` cannot. Like `verdict_runner` it imports no rclpy.

Roles (one process each, typically on different machines):

  --role converter
      Consume DataRecords from `verdict_runner.source` (the robot's MQTT
      stream), run each converter, and publish its DSL-ready records to the
      converter's `dsl_transport` topic.

  --role verdict
      Subscribe to each converter's `dsl_transport` topic, run the paired
      verdict stage, and export verdicts.

Each converter entry that should be split carries a `dsl_transport:` block
giving the MQTT topic that joins the two halves:

    verdict_runner:
      source:                      # only read by --role converter
        type: mqtt
        broker: 127.0.0.1
        topic_filter: monitor/#

    converters:
      - type: custom.odom_speed_converter:OdomSpeedConverter
        dsl_transport:             # the seam between the two hosts
          broker: 127.0.0.1
          topic: dsl/odom_speed
        verdict:                   # only run by --role verdict
          type: custom.odom_speed_verdict:OdomSpeedVerdict
          exporters:
            - type: stdout

Supported `dsl_transport` keys: topic (required), broker, port, qos, keepalive.
The same YAML file can be deployed to both hosts; each role reads only the
parts it needs.
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading

import yaml

from config_model import ConverterSpec, RunnerConfig
from data_record import generate_session_id
from dsl_transport import DslRecordMQTTExporter, DslRecordMQTTSource
from exporter import Dispatcher, Exporter, FileExporter
from exporter_mqtt import MQTTExporter
from pipeline import build_converter_stage, build_verdict_stage
from sources import resolve_source_class

logger = logging.getLogger("split_runner")


def _transport_kwargs(spec: ConverterSpec) -> dict | None:
    dt = spec.dsl_transport
    if not dt or not dt.get("topic"):
        logger.error(
            "Converter '%s' needs a 'dsl_transport' block with a 'topic' for "
            "split deployment; skipping.", spec.type or "?",
        )
        return None
    allowed = {"topic", "broker", "port", "qos", "keepalive"}
    return {k: v for k, v in dt.items() if k in allowed}


def _build_filter_output(spec: ConverterSpec) -> Exporter | None:
    """Build the DataRecord exporter a filter republishes through, picking file
    vs mqtt from the `record_transport.kind`."""
    rt = spec.record_transport
    if not rt:
        logger.error(
            "Converter '%s' needs a 'record_transport' block to run as "
            "--role filter; skipping.", spec.type or "?",
        )
        return None
    kind = rt.get("kind", "mqtt")
    if kind == "file":
        allowed = {"output_dir", "session_id", "filename_suffix", "flush_every"}
        kwargs = {k: v for k, v in rt.items() if k in allowed}
        if not kwargs.get("output_dir") or not kwargs.get("session_id"):
            logger.error(
                "Converter '%s' file record_transport needs 'output_dir' and "
                "'session_id'; skipping.", spec.type or "?",
            )
            return None
        kwargs.setdefault("filename_suffix", "")
        return FileExporter(**kwargs)
    allowed = {"topic_prefix", "broker", "port", "qos", "keepalive"}
    kwargs = {k: v for k, v in rt.items() if k in allowed}
    if not kwargs.get("topic_prefix"):
        logger.error(
            "Converter '%s' mqtt record_transport needs a 'topic_prefix'; "
            "skipping.", spec.type or "?",
        )
        return None
    return MQTTExporter(**kwargs)


def _run_filter_role(cfg: RunnerConfig, stop_event: threading.Event) -> int:
    """Filter host: DataRecord source -> data_filter converters -> republish
    DataRecords. The seam to the *next* converter is the existing DataRecord
    MQTT transport, so the downstream host reads it exactly like a monitor feed.
    """
    if cfg.source is None or not cfg.source.type:
        logger.error("--role filter needs 'verdict_runner.source' with a 'type'.")
        return 1
    try:
        source_cls = resolve_source_class(cfg.source.type)
        source = source_cls(**cfg.source.kwargs)
    except Exception as ex:
        logger.error("Failed to build source '%s': %s", cfg.source.type, ex)
        return 1

    raw_dispatcher: Dispatcher = Dispatcher(label="SplitFilterDispatcher")
    publish_dispatchers: list[Dispatcher] = []
    built = 0
    for spec in cfg.converters:
        out_exporter = _build_filter_output(spec)
        if out_exporter is None:
            continue
        downstream: Dispatcher = Dispatcher(label=f"RecordOut[{spec.type}]")
        downstream.add(out_exporter)
        outer = build_converter_stage(spec, downstream, logger)
        if outer is None:
            downstream.close_all()
            continue
        raw_dispatcher.add(outer)
        publish_dispatchers.append(downstream)
        built += 1
        logger.info("Filter '%s' republishing records", spec.type)

    if built == 0:
        logger.error("No filter stages built; exiting.")
        return 1

    source.start(raw_dispatcher)
    logger.info("Filter role started (%d filter(s)).", built)
    try:
        stop_event.wait()
    finally:
        source.stop()
        for d in publish_dispatchers:
            d.close_all()
    return 0


def _run_converter_role(cfg: RunnerConfig, stop_event: threading.Event) -> int:
    """Converter host: DataRecord source -> converters -> publish DSL records."""
    if cfg.source is None or not cfg.source.type:
        logger.error("--role converter needs 'verdict_runner.source' with a 'type'.")
        return 1
    try:
        source_cls = resolve_source_class(cfg.source.type)
        source = source_cls(**cfg.source.kwargs)
    except Exception as ex:
        logger.error("Failed to build source '%s': %s", cfg.source.type, ex)
        return 1

    raw_dispatcher: Dispatcher = Dispatcher(label="SplitConverterDispatcher")
    publish_dispatchers: list[Dispatcher] = []
    built = 0
    for spec in cfg.converters:
        kwargs = _transport_kwargs(spec)
        if kwargs is None:
            continue
        downstream: Dispatcher = Dispatcher(label=f"DslOut[{spec.type}]")
        downstream.add(DslRecordMQTTExporter(**kwargs))
        outer = build_converter_stage(spec, downstream, logger)
        if outer is None:
            downstream.close_all()
            continue
        raw_dispatcher.add(outer)
        publish_dispatchers.append(downstream)
        built += 1
        logger.info("Converter '%s' -> dsl topic '%s'", spec.type, kwargs["topic"])

    if built == 0:
        logger.error("No converter stages built; exiting.")
        return 1

    source.start(raw_dispatcher)
    logger.info("Converter role started (%d converter(s)).", built)
    try:
        stop_event.wait()
    finally:
        source.stop()
        for d in publish_dispatchers:
            d.close_all()
    return 0


def _run_verdict_role(cfg: RunnerConfig, stop_event: threading.Event) -> int:
    """Verdict host: subscribe DSL records -> verdict stage -> verdicts."""
    session_id = generate_session_id()
    sources: list[DslRecordMQTTSource] = []
    dsl_dispatchers: list[Dispatcher] = []
    verdict_dispatchers: list[Dispatcher] = []
    built = 0
    for spec in cfg.converters:
        kwargs = _transport_kwargs(spec)
        if kwargs is None:
            continue
        stage = build_verdict_stage(spec, cfg.output_dir, session_id, logger)
        if stage is None:
            continue
        dsl_dispatcher, verdict_dispatcher = stage
        src = DslRecordMQTTSource(**kwargs)
        src.start(dsl_dispatcher)
        sources.append(src)
        dsl_dispatchers.append(dsl_dispatcher)
        verdict_dispatchers.append(verdict_dispatcher)
        built += 1
        logger.info("Verdict stage for '%s' <- dsl topic '%s'", spec.type, kwargs["topic"])

    if built == 0:
        logger.error("No verdict stages built; exiting.")
        return 1

    logger.info("Verdict role started session_id=%s (%d stage(s)).", session_id, built)
    try:
        stop_event.wait()
    finally:
        for src in sources:
            src.stop()
        for d in dsl_dispatchers:
            d.close_all()
        for d in verdict_dispatchers:
            d.close_all()
    return 0


def main() -> int:
    logging.basicConfig(
        level=os.environ.get("SPLIT_RUNNER_LOG", "INFO"),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="Split-deployment runner")
    parser.add_argument(
        "--role", "-r", required=True, choices=["converter", "verdict", "filter"],
        help="Which part of the split chain to run on this host.",
    )
    parser.add_argument(
        "--config", "-c",
        default=os.environ.get("MONITOR_CONFIG", "./monitor/config.yaml"),
        help="Path to YAML config file (default: $MONITOR_CONFIG or ./monitor/config.yaml)",
    )
    args = parser.parse_args()

    project_root = os.getcwd()
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    try:
        cfg = RunnerConfig.load(args.config)
    except FileNotFoundError:
        print(f"Error: config not found at {args.config}", file=sys.stderr)
        return 1
    except yaml.YAMLError as ex:
        print(f"Error: config parse failed: {ex}", file=sys.stderr)
        return 1

    if not cfg.converters:
        logger.error("No 'converters:' configured; nothing to do.")
        return 1

    stop_event = threading.Event()

    def _on_signal(*_):
        logger.info("Signal received; stopping.")
        stop_event.set()

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    if args.role == "converter":
        return _run_converter_role(cfg, stop_event)
    if args.role == "filter":
        return _run_filter_role(cfg, stop_event)
    return _run_verdict_role(cfg, stop_event)


if __name__ == "__main__":
    sys.exit(main())
