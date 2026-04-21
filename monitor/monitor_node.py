"""MonitorNode — orchestrates the 4-layer monitoring pipeline.

ROS2 Application -> DataCollector -> TransformerPipeline -> ExportDispatcher -> Exporter(s)

Responsibilities:
    1. Load MonitorConfig from YAML.
    2. Generate a session_id and build the ExportDispatcher with configured exporters.
    3. Instantiate one Collector per configured topic/service/action, each with its
       own TransformerPipeline.
    4. Emit session_start, spin, and on shutdown emit session_end + close exporters.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any

import yaml
import rclpy
from rclpy.node import Node

from data_record import DataRecord, generate_session_id
from collector import (
    CollectorManager,
    TopicCollector,
    ServiceCollector,
    ActionCollector,
)
from transformer import (
    Transformer,
    TransformerPipeline,
    FieldExtractor,
    RateThrottler,
    OnChangeFilter,
)
from exporter import Exporter, ExportDispatcher, FileExporter
from exporter_mqtt import MQTTExporter


TRANSFORMER_REGISTRY: dict[str, type[Transformer]] = {
    "FieldExtractor": FieldExtractor,
    "RateThrottler": RateThrottler,
    "OnChangeFilter": OnChangeFilter,
}

EXPORTER_REGISTRY: dict[str, type[Exporter]] = {
    "file": FileExporter,
    "mqtt": MQTTExporter,
}


@dataclass
class MonitorConfig:
    raw: dict
    output_dir: str = "./output"
    session_id_prefix: str = ""
    topics: list[dict] = field(default_factory=list)
    services: list[dict] = field(default_factory=list)
    actions: list[dict] = field(default_factory=list)
    exporters: list[dict] = field(default_factory=list)

    @classmethod
    def load(cls, yaml_path: str) -> "MonitorConfig":
        with open(yaml_path, "r") as f:
            data = yaml.safe_load(f) or {}
        monitor = data.get("monitor", {}) or {}
        return cls(
            raw=data,
            output_dir=monitor.get("output_dir", "./output"),
            session_id_prefix=monitor.get("session_id_prefix", ""),
            topics=list(data.get("topics") or []),
            services=list(data.get("services") or []),
            actions=list(data.get("actions") or []),
            exporters=list(data.get("exporters") or []),
        )


def _build_pipeline(specs: list[dict] | None, logger) -> TransformerPipeline:
    chain: list[Transformer] = []
    for spec in specs or []:
        t_type = spec.get("type")
        if not t_type:
            logger.warn(f"Transformer spec missing 'type'; skipping: {spec}")
            continue
        cls = TRANSFORMER_REGISTRY.get(t_type)
        if cls is None:
            logger.warn(f"Unknown transformer type: {t_type}; skipping.")
            continue
        kwargs = {k: v for k, v in spec.items() if k != "type"}
        try:
            chain.append(cls(**kwargs))
        except Exception as ex:
            logger.error(f"Failed to build transformer {t_type}: {ex}")
    return TransformerPipeline(chain)


def _build_dispatcher(
    specs: list[dict],
    output_dir: str,
    session_id: str,
    logger,
) -> ExportDispatcher:
    dispatcher = ExportDispatcher()
    for name, cls in EXPORTER_REGISTRY.items():
        dispatcher.register(name, cls)

    # Default to file exporter if none configured
    if not specs:
        specs = [{"type": "file"}]

    for spec in specs:
        name = spec.get("type")
        if not name:
            logger.warn(f"Exporter spec missing 'type'; skipping: {spec}")
            continue
        if not dispatcher.has(name):
            logger.warn(f"Unknown exporter type: {name}; skipping.")
            continue
        kwargs: dict[str, Any] = {k: v for k, v in spec.items() if k != "type"}
        if name == "file":
            kwargs.setdefault("output_dir", output_dir)
            kwargs.setdefault("session_id", session_id)
        try:
            dispatcher.add(dispatcher.build(name, **kwargs))
            logger.info(f"Exporter enabled: {name}")
        except Exception as ex:
            logger.error(f"Failed to build exporter {name}: {ex}")
    return dispatcher


class MonitorNode(Node):
    def __init__(self, config: MonitorConfig):
        super().__init__("ros2_monitor_node")
        self.config = config
        log = self.get_logger()

        base_id = generate_session_id()
        self.session_id = (
            f"{config.session_id_prefix}_{base_id}"
            if config.session_id_prefix else base_id
        )
        log.info(f"Monitor starting — session_id={self.session_id}")

        self.dispatcher = _build_dispatcher(
            config.exporters, config.output_dir, self.session_id, log
        )

        # session_start bypasses any pipeline
        self.dispatcher.dispatch(
            DataRecord.make_session_start(self.session_id, config.raw)
        )

        self.manager = CollectorManager(
            self, self.session_id, self.dispatcher.dispatch
        )

        # Topic types can be auto-discovered from the network if not set
        self._active_topic_types = self._discover_topic_types()

        for spec in config.topics:
            self._register_topic(spec)
        for spec in config.services:
            self._register_service(spec)
        for spec in config.actions:
            self._register_action(spec)

        self.manager.start_all()
        log.info(
            f"Registered {len(self.manager.collectors)} collector(s); spinning."
        )

    def _discover_topic_types(self) -> dict[str, str]:
        import time
        time.sleep(1.0)  # allow DDS discovery
        return {
            name: types[0]
            for name, types in self.get_topic_names_and_types()
            if types
        }

    def _register_topic(self, spec: dict) -> None:
        log = self.get_logger()
        name = spec.get("name")
        if not name:
            log.error("Topic spec missing 'name'; skipping.")
            return
        msg_type = spec.get("type") or self._active_topic_types.get(name)
        if not msg_type:
            log.error(
                f"Cannot determine type for {name}: not active at startup and "
                f"no 'type' in config; skipping."
            )
            return
        pipeline = _build_pipeline(spec.get("transformers"), log)
        collector = TopicCollector(
            node=self,
            session_id=self.session_id,
            source_name=name,
            msg_type_str=msg_type,
            pipeline=pipeline,
            dispatch=self.dispatcher.dispatch,
            qos=int(spec.get("qos", 10)),
        )
        self.manager.register(collector)
        log.info(f"  Topic: {name} [{msg_type}]")

    def _register_service(self, spec: dict) -> None:
        log = self.get_logger()
        name = spec.get("name")
        srv_type = spec.get("type")
        if not name or not srv_type:
            log.error(
                f"Service spec requires 'name' and 'type' (e.g. "
                f"'std_srvs/srv/SetBool'); got {spec}; skipping."
            )
            return
        pipeline = _build_pipeline(spec.get("transformers"), log)
        collector = ServiceCollector(
            node=self,
            session_id=self.session_id,
            source_name=name,
            service_type_str=srv_type,
            pipeline=pipeline,
            dispatch=self.dispatcher.dispatch,
        )
        self.manager.register(collector)
        log.info(f"  Service: {name} [{srv_type}]")

    def _register_action(self, spec: dict) -> None:
        log = self.get_logger()
        name = spec.get("name")
        act_type = spec.get("type")
        if not name or not act_type:
            log.error(
                f"Action spec requires 'name' and 'type'; got {spec}; skipping."
            )
            return
        phases = spec.get("phases") or ["feedback", "status"]
        pipeline = _build_pipeline(spec.get("transformers"), log)
        collector = ActionCollector(
            node=self,
            session_id=self.session_id,
            source_name=name,
            action_type_str=act_type,
            phases=phases,
            pipeline=pipeline,
            dispatch=self.dispatcher.dispatch,
        )
        self.manager.register(collector)
        log.info(f"  Action: {name} [{act_type}] phases={phases}")

    def shutdown(self) -> None:
        try:
            self.manager.stop_all()
        finally:
            self.dispatcher.dispatch(
                DataRecord.make_session_end(self.session_id, {
                    "collectors": len(self.manager.collectors),
                })
            )
            self.dispatcher.close_all()


def main() -> int:
    config_path = os.environ.get("MONITOR_CONFIG", "./monitor/config.yaml")
    try:
        config = MonitorConfig.load(config_path)
    except FileNotFoundError:
        print(f"Error: config file not found at {config_path}", file=sys.stderr)
        return 1
    except yaml.YAMLError as ex:
        print(f"Error: failed to parse config: {ex}", file=sys.stderr)
        return 1

    rclpy.init()
    node: MonitorNode | None = None
    try:
        node = MonitorNode(config)
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.shutdown()
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
