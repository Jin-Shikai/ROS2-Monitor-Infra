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
from exporter import Dispatcher, Exporter, FileExporter
from exporter_mqtt import MQTTExporter
from pipeline import build_converter_chain


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
    converters: list[dict] = field(default_factory=list)

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
            converters=list(data.get("converters") or []),
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


def _sanitize_source_name(source_name: str) -> str:
    """Turn an ROS source name (e.g. '/navigate_to_pose') into a safe
    filename suffix (e.g. '_navigate_to_pose')."""
    return source_name.replace("/", "_") or "_root"


def _build_dispatcher(
    specs: list[dict],
    output_dir: str,
    session_id: str,
    logger,
    label: str = "ExportDispatcher",
    source_name: str | None = None,
) -> Dispatcher:
    """Build a Dispatcher[DataRecord] from a list of exporter specs.

    When `source_name` is given (per-source dispatcher), file exporters
    that don't explicitly set `filename_suffix` get one derived from
    the source name, so each topic writes to its own JSONL file.
    """
    dispatcher: Dispatcher = Dispatcher(label=label)
    for name, cls in EXPORTER_REGISTRY.items():
        dispatcher.register(name, cls)

    # Default to file exporter if none configured (only at global scope)
    if not specs:
        if source_name is not None:
            return dispatcher  # per-source: no exporters means "use global only"
        specs = [{"type": "file"}]

    suffix_default = (
        _sanitize_source_name(source_name) if source_name is not None else ""
    )
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
            if suffix_default:
                kwargs.setdefault("filename_suffix", suffix_default)
        try:
            dispatcher.add(dispatcher.build(name, **kwargs))
            logger.info(
                f"Exporter enabled: {name}"
                + (f" (source={source_name})" if source_name else "")
            )
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

        # Converter chains live on a dedicated tap, *not* on the global
        # exporters dispatcher. This way a record routed to a per-source
        # dispatcher (bypassing global exporters) still reaches the
        # converter / verdict pipeline.
        self._converter_dispatcher: Dispatcher = Dispatcher(label="Converters")

        # Track per-source dispatchers (one per topic/service/action
        # whose spec has its own `exporters:` block). Records on those
        # sources go *only* to the per-source dispatcher, not to the
        # global exporters — but they are still tee'd to converters.
        self._source_dispatchers: list[Dispatcher] = []

        # Track per-chain verdict dispatchers so we can close their
        # transports (file handles, MQTT clients, ...) on shutdown.
        self._verdict_dispatchers: list[Dispatcher] = []
        for spec in config.converters:
            built = build_converter_chain(
                spec, config.output_dir, self.session_id, log
            )
            if built is None:
                continue
            converter_exporter, verdict_dispatcher = built
            self._converter_dispatcher.add(converter_exporter)
            self._verdict_dispatchers.append(verdict_dispatcher)

        # session_start bypasses any pipeline (converters skip non-data
        # records anyway, so no tee needed here)
        self.dispatcher.dispatch(
            DataRecord.make_session_start(self.session_id, config.raw)
        )

        self.manager = CollectorManager(
            self, self.session_id, self.dispatcher.dispatch
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

    def _dispatch_for(self, spec: dict, source_name: str, log) -> Any:
        """Return a `dispatch` callable for one source.

        If the spec carries its own `exporters:` block, build a per-source
        Dispatcher (records go *only* there for the exporter side,
        isolated from the global stream). Either way the record is also
        tee'd to the converter tap so DSL chains keep working.
        """
        per_source_specs = spec.get("exporters")
        if per_source_specs:
            sub = _build_dispatcher(
                per_source_specs,
                self.config.output_dir,
                self.session_id,
                log,
                label=f"Exporters[{source_name}]",
                source_name=source_name,
            )
            self._source_dispatchers.append(sub)
            target = sub.dispatch
        else:
            target = self.dispatcher.dispatch
        converter_dispatch = self._converter_dispatcher.dispatch

        def tee(record):
            target(record)
            converter_dispatch(record)
        return tee

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
            dispatch=self._dispatch_for(spec, name, log),
            qos=int(spec.get("qos", 10)),
        )
        self.manager.register(collector)
        log.info(f"  Topic: {name} [{msg_type}]")

    def _register_service(self, spec: dict) -> None:
        log = self.get_logger()
        name = spec.get("name")
        if not name:
            log.error(f"Service spec missing 'name'; skipping.")
            return
        srv_type = spec.get("type") or self._active_service_types.get(name)
        if not srv_type:
            log.error(
                f"Cannot determine type for service {name}: not active at startup "
                f"and no 'type' in config; skipping."
            )
            return
        pipeline = _build_pipeline(spec.get("transformers"), log)
        collector = ServiceCollector(
            node=self,
            session_id=self.session_id,
            source_name=name,
            service_type_str=srv_type,
            pipeline=pipeline,
            dispatch=self._dispatch_for(spec, name, log),
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
            dispatch=self._dispatch_for(spec, name, log),
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
            self._converter_dispatcher.close_all()
            for sd in self._source_dispatchers:
                sd.close_all()
            for vd in self._verdict_dispatchers:
                vd.close_all()


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
    try:
        node = MonitorNode(config)
        rclpy.spin(node)
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
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
