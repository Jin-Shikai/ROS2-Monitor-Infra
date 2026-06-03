"""Verdict-side runner — consumes records via a pluggable Source and evaluates DSL chains.

This script does **not** import rclpy. It is intended to run on a separate
host from the ROS2 monitor: the only runtime requirements are Python +
whatever the configured `Source` needs (paho-mqtt for the built-in `mqtt`
source) + the user's DSL classes.

The same YAML used by `monitor_node` is consumed; only `monitor.output_dir`,
`converters:` and `verdict_runner.source:` are read.

Topology (with the built-in MQTT source):

    monitor_node (robot box)
      Collector -> Transformer -> Dispatcher[DataRecord] -> MQTTExporter
                                                                |
                                                                v
                                                          MQTT broker
                                                                |
                                                                v
    verdict_runner (verdict box)
      Source -> Dispatcher[DataRecord] -> ConverterExporter -> ...
                                                          -> VerdictService
                                                          -> Dispatcher[Verdict]
                                                                |--> VerdictFileExporter
                                                                `--> ... (mqtt / user)

The source is fully pluggable: any `Source[DataRecord]` subclass —
built-in or `module.path:ClassName` — can replace MQTT (e.g. UDP socket,
file replay, ROS2 topic on the verdict box).
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
from dataclasses import dataclass, field
from typing import Any

import yaml

from data_record import generate_session_id
from exporter import Dispatcher
from pipeline import build_converter_chain
from sources import resolve_source_class

logger = logging.getLogger("verdict_runner")


@dataclass
class RunnerConfig:
    output_dir: str
    converters: list[dict]
    source: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, yaml_path: str) -> "RunnerConfig":
        with open(yaml_path, "r") as f:
            data = yaml.safe_load(f) or {}
        monitor = data.get("monitor", {}) or {}
        runner = data.get("verdict_runner", {}) or {}
        source_spec = runner.get("source") or {}
        return cls(
            output_dir=monitor.get("output_dir", "./output"),
            converters=list(data.get("converters") or []),
            source=dict(source_spec),
        )


def main() -> int:
    logging.basicConfig(
        level=os.environ.get("VERDICT_RUNNER_LOG", "INFO"),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="Verdict-side runner")
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
        logger.error("No 'converters:' configured; nothing to evaluate.")
        return 1

    source_kwargs = dict(cfg.source)
    source_type = source_kwargs.pop("type", None)
    if not source_type:
        logger.error("'verdict_runner.source' must include a 'type'.")
        return 1
    try:
        source_cls = resolve_source_class(source_type)
    except (KeyError, ImportError, AttributeError, TypeError, ValueError) as ex:
        logger.error("Cannot resolve source '%s': %s", source_type, ex)
        return 1
    try:
        source = source_cls(**source_kwargs)
    except Exception as ex:
        logger.error("Failed to build source '%s': %s", source_type, ex)
        return 1

    runner_session_id = generate_session_id()
    logger.info("Verdict runner session_id=%s source=%s", runner_session_id, source_type)

    raw_dispatcher: Dispatcher = Dispatcher(label="VerdictRunnerDispatcher")
    verdict_dispatchers: list[Dispatcher] = []
    chains_built = 0
    for spec in cfg.converters:
        built = build_converter_chain(
            spec, cfg.output_dir, runner_session_id, logger,
        )
        if built is None:
            continue
        ce, vd = built
        raw_dispatcher.add(ce)
        verdict_dispatchers.append(vd)
        chains_built += 1

    if chains_built == 0:
        logger.error("No converter chains built; exiting.")
        return 1

    stop_event = threading.Event()

    def _on_signal(*_):
        logger.info("Signal received; stopping.")
        stop_event.set()

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    source.start(raw_dispatcher)
    logger.info("Source '%s' started.", source_type)
    try:
        stop_event.wait()
    finally:
        source.stop()
        raw_dispatcher.close_all()
        for vd in verdict_dispatchers:
            vd.close_all()
    return 0


if __name__ == "__main__":
    sys.exit(main())
