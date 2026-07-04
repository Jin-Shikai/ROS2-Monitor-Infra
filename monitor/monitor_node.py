"""MonitorNode — orchestrates the 4-layer monitoring pipeline.

ROS2 Application -> DataCollector -> TransformerPipeline -> Dispatcher -> Exporter(s)

Responsibilities:
    1. Load MonitorConfig from YAML.
    2. Generate a session_id and build the Dispatcher with configured exporters.
    3. Instantiate one Collector per configured topic/service/action, each with its
       own TransformerPipeline.
    4. Emit session_start, spin, and on shutdown emit session_end + close exporters.
"""

from __future__ import annotations

import os
import sys
from typing import Any

import yaml
import rclpy
from rclpy.node import Node

from config_model import MonitorConfig, MonitoredSourceSpec
from data_record import generate_session_id
from collector import (
    CollectorManager,
    TopicCollector,
    ServiceCollector,
    ActionCollector,
)
from runtime_builder import (
    MonitorRuntime,
    build_transformer_pipeline,
)


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

        self.runtime = MonitorRuntime(config, self.session_id, log)
        self.dispatcher = self.runtime.dispatcher
        self.runtime.emit_session_start()

        self.manager = CollectorManager(
            self, self.session_id, self.dispatcher.export
        )

        # Types can be auto-discovered from the network if not set in config
        self._active_topic_types, self._active_service_types = self._discover_network_types()

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

    def _export_for(
        self,
        spec: MonitoredSourceSpec,
        source_name: str,
        log,
    ) -> Any:
        """Return an export callable for one source.

        If the spec carries its own `exporters:` block, build a per-source
        Dispatcher (records go *only* there for the exporter side,
        isolated from the global stream). Either way the record is also
        tee'd to the converter tap so evaluation graphs keep working.
        """
        return self.runtime.export_for(spec, source_name).export

    def _discover_network_types(self) -> tuple[dict[str, str], dict[str, str]]:
        import time
        time.sleep(1.0)  # allow DDS discovery
        topic_types = {
            name: types[0]
            for name, types in self.get_topic_names_and_types()
            if types
        }
        service_types = {
            name: types[0]
            for name, types in self.get_service_names_and_types()
            if types
        }
        return topic_types, service_types

    def _register_topic(self, spec: MonitoredSourceSpec) -> None:
        log = self.get_logger()
        name = spec.name
        if not name:
            log.error("Topic spec missing 'name'; skipping.")
            return
        msg_type = spec.msg_type or self._active_topic_types.get(name)
        if not msg_type:
            log.error(
                f"Cannot determine type for {name}: not active at startup and "
                f"no 'type' in config; skipping."
            )
            return
        pipeline = build_transformer_pipeline(spec.transformers, log)
        collector = TopicCollector(
            node=self,
            session_id=self.session_id,
            source_name=name,
            msg_type_str=msg_type,
            pipeline=pipeline,
            export=self._export_for(spec, name, log),
            qos=int(spec.qos or 10),
        )
        self.manager.register(collector)
        log.info(f"  Topic: {name} [{msg_type}]")

    def _register_service(self, spec: MonitoredSourceSpec) -> None:
        log = self.get_logger()
        name = spec.name
        if not name:
            log.error(f"Service spec missing 'name'; skipping.")
            return
        srv_type = spec.msg_type or self._active_service_types.get(name)
        if not srv_type:
            log.error(
                f"Cannot determine type for service {name}: not active at startup "
                f"and no 'type' in config; skipping."
            )
            return
        pipeline = build_transformer_pipeline(spec.transformers, log)
        collector = ServiceCollector(
            node=self,
            session_id=self.session_id,
            source_name=name,
            service_type_str=srv_type,
            pipeline=pipeline,
            export=self._export_for(spec, name, log),
        )
        self.manager.register(collector)
        log.info(f"  Service: {name} [{srv_type}]")

    def _register_action(self, spec: MonitoredSourceSpec) -> None:
        log = self.get_logger()
        name = spec.name
        act_type = spec.msg_type
        if not name or not act_type:
            log.error(
                f"Action spec requires 'name' and 'type'; got {spec}; skipping."
            )
            return
        phases = spec.phases or ["feedback", "status"]
        pipeline = build_transformer_pipeline(spec.transformers, log)
        collector = ActionCollector(
            node=self,
            session_id=self.session_id,
            source_name=name,
            action_type_str=act_type,
            phases=phases,
            pipeline=pipeline,
            export=self._export_for(spec, name, log),
        )
        self.manager.register(collector)
        log.info(f"  Action: {name} [{act_type}] phases={phases}")

    def shutdown(self) -> None:
        try:
            self.manager.stop_all()
        finally:
            stats = {"collectors": len(self.manager.collectors)}
            self.runtime.emit_session_end(stats)
            self.runtime.close_all()


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="ROS2 Monitor Node")
    parser.add_argument(
        "--config", "-c",
        default=os.environ.get("MONITOR_CONFIG", "./monitor/config.yaml"),
        help="Path to YAML config file (default: $MONITOR_CONFIG or ./monitor/config.yaml)",
    )
    args = parser.parse_args()
    config_path = args.config

    # Make user-supplied modules under <project_root>/custom/ importable via
    # 'custom.x:Class' in config. Project root = cwd at launch (the recipe is
    # `cd ~/ROS2-Monitor-Infra && python3 monitor/monitor_node.py`).
    project_root = os.getcwd()
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
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

    from rclpy.executors import ExternalShutdownException
    try:
        node = MonitorNode(config)
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
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
