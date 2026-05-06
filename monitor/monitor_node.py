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
from converter import ConverterExporter, resolve_converter_class
from verdict import (
    FileVerdictSink,
    VerdictExporter,
    resolve_verdict_class,
)


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


def _build_dispatcher(
    specs: list[dict],
    output_dir: str,
    session_id: str,
    logger,
) -> Dispatcher:
    dispatcher: Dispatcher = Dispatcher(label="ExportDispatcher")
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


def _build_converter_chain(
    spec: dict,
    output_dir: str,
    session_id: str,
    logger,
) -> tuple[ConverterExporter, list[FileVerdictSink]] | None:
    """Build one DSL chain: DataConverter -> Dispatcher[Any] -> [VerdictExporter, ...].

    Returns the ConverterExporter (to be registered on the raw dispatcher) plus
    any FileVerdictSinks that need closing on shutdown. Returns None on error.
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
    except (KeyError, ImportError, AttributeError, TypeError) as ex:
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
    except (KeyError, ImportError, AttributeError, TypeError) as ex:
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
        from pathlib import Path
        out_path = Path(verdict_output)
        if not out_path.is_absolute():
            out_path = Path(output_dir) / verdict_output
        # Stamp session_id into the filename if a placeholder is present.
        out_path = Path(str(out_path).replace("{session_id}", session_id))
        sink_obj = FileVerdictSink(str(out_path))
        sinks.append(sink_obj)
        sink = sink_obj

    dsl_dispatcher: Dispatcher = Dispatcher(label=f"DSL[{converter_type}]")
    dsl_dispatcher.add(VerdictExporter(verdict_service, sink=sink))

    # Optional: also archive dsl records to a file for offline replay.
    dsl_record_output = spec.get("output")
    if dsl_record_output:
        from pathlib import Path
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

        # Track verdict sinks so we can close their file handles on shutdown.
        self._verdict_sinks: list[FileVerdictSink] = []
        for spec in config.converters:
            built = _build_converter_chain(
                spec, config.output_dir, self.session_id, log
            )
            if built is None:
                continue
            converter_exporter, sinks = built
            self.dispatcher.add(converter_exporter)
            self._verdict_sinks.extend(sinks)

        # session_start bypasses any pipeline
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
            dispatch=self.dispatcher.dispatch,
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
            for sink in self._verdict_sinks:
                sink.close()


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
