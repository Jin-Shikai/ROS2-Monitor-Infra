"""Unified rclpy-free runner: inbound endpoints -> node graph -> outbound endpoints.

One process runs any mix of converters and verdict services declared in one
YAML — a filter relay, a converter half, a verdict half, or a full chain —
so a deployment places runtimes on hosts freely instead of choosing a
per-process role. The only runtime requirements are Python + whatever the
configured transports need (paho-mqtt for the built-in `mqtt` endpoints) +
the user's converter/verdict classes.

    inputs (records) ----> record_entry -> converters -> verdicts -> exporters
    inputs (dsl)     ----> input_entries[<id>] --links--> verdicts / outputs
    converters --links--> converters / verdicts / outputs (records or dsl)

See `pipeline.build_graph` for the node/link semantics.
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
from typing import Any

import yaml

from config_model import RunnerConfig
from data_record import generate_session_id
from dsl_transport import resolve_dsl_source_class
from pipeline import build_graph
from source import Source
from sources import resolve_source_class

logger = logging.getLogger("node_runner")


def run(cfg: RunnerConfig, stop_event: threading.Event, log: Any = logger) -> int:
    session_id = generate_session_id()
    runtime = build_graph(
        cfg.converters,
        cfg.verdict_services,
        cfg.links,
        cfg.outputs,
        cfg.output_dir,
        session_id,
        log,
    )
    if runtime is None:
        log.error("No usable node graph built; exiting.")
        return 1

    sources: list[Source] = []
    for spec in cfg.inputs:
        if not spec.type:
            log.error(f"Input '{spec.id}' missing 'type'; skipping.")
            continue
        try:
            if spec.payload == "dsl":
                entry = runtime.input_entries.get(spec.id)
                if entry is None or entry.is_empty():
                    log.error(
                        f"Input '{spec.id}' (dsl) has no 'input:{spec.id} -> ...' "
                        "link; skipping."
                    )
                    continue
                source = resolve_dsl_source_class(spec.type)(**spec.kwargs)
            elif spec.payload == "records":
                entry = runtime.record_entry
                source = resolve_source_class(spec.type)(**spec.kwargs)
            else:
                log.error(
                    f"Input '{spec.id}' has unsupported payload '{spec.payload}' "
                    "(supported: records, dsl); skipping."
                )
                continue
        except Exception as ex:
            log.error(f"Failed to build input '{spec.id}' ({spec.type}): {ex}")
            continue
        source.start(entry)
        sources.append(source)
        log.info(f"Input '{spec.id}': {spec.payload} via {spec.type}")

    if not sources:
        log.error("No inputs started; exiting.")
        runtime.close()
        return 1

    log.info(
        f"Node runner started session_id={session_id} "
        f"({len(sources)} input(s), {runtime.converter_count} converter(s), "
        f"{len(cfg.verdict_services)} verdict service(s))."
    )
    try:
        stop_event.wait()
    finally:
        for source in sources:
            source.stop()
        runtime.close()
    return 0


def main() -> int:
    logging.basicConfig(
        level=os.environ.get("NODE_RUNNER_LOG", "INFO"),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="Unified monitor node runner")
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

    stop_event = threading.Event()

    def _on_signal(*_):
        logger.info("Signal received; stopping.")
        stop_event.set()

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    return run(cfg, stop_event)


if __name__ == "__main__":
    sys.exit(main())
