"""Verdict-side runner — consumes DataRecords over MQTT and evaluates DSL chains.

This script does **not** import rclpy. It is intended to run on a separate
host from the ROS2 monitor: the only runtime requirements are Python +
paho-mqtt + the user's DSL classes (and their transitive dependencies).

The same YAML used by `monitor_node` is consumed; only the `monitor.output_dir`,
`converters:` and the new `verdict_runner:` sections are read.

Topology:

    monitor_node (robot box)
      Collector -> Transformer -> Dispatcher[DataRecord] -> MQTTExporter
                                                                |
                                                                v
                                                          MQTT broker
                                                                |
                                                                v
    verdict_runner (verdict box)
      MQTTSource -> Dispatcher[DataRecord] -> ConverterExporter -> ...
                                                          -> VerdictService
                                                          -> Dispatcher[Verdict]
                                                                |--> VerdictFileExporter
                                                                `--> ... (mqtt / user)
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
from dataclasses import dataclass

import yaml

from data_record import generate_session_id
from exporter import Dispatcher
from pipeline import build_converter_chain
from source_mqtt import MQTTSource

logger = logging.getLogger("verdict_runner")


@dataclass
class RunnerConfig:
    output_dir: str
    converters: list[dict]
    broker: str
    port: int
    topic_filter: str
    qos: int

    @classmethod
    def load(cls, yaml_path: str) -> "RunnerConfig":
        with open(yaml_path, "r") as f:
            data = yaml.safe_load(f) or {}
        monitor = data.get("monitor", {}) or {}
        runner = data.get("verdict_runner", {}) or {}
        return cls(
            output_dir=monitor.get("output_dir", "./output"),
            converters=list(data.get("converters") or []),
            broker=runner.get("broker", "localhost"),
            port=int(runner.get("port", 1883)),
            topic_filter=runner.get("topic_filter", "monitor/#"),
            qos=int(runner.get("qos", 1)),
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

    runner_session_id = generate_session_id()
    logger.info("Verdict runner session_id=%s", runner_session_id)

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

    source = MQTTSource(
        broker=cfg.broker,
        port=cfg.port,
        topic_filter=cfg.topic_filter,
        qos=cfg.qos,
    )

    stop_event = threading.Event()

    def _on_signal(*_):
        logger.info("Signal received; stopping.")
        stop_event.set()

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    source.start(raw_dispatcher.dispatch)
    logger.info(
        "MQTTSource started: broker=%s:%d filter=%s",
        cfg.broker, cfg.port, cfg.topic_filter,
    )
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
