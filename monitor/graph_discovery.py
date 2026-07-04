"""Discover visible ROS 2 graph resources and print JSON.

This helper is intentionally tiny so the showcase control plane can run it
either in a sourced local ROS 2 environment or inside the project Docker image.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from typing import Any


DISCOVERY_NODE_NAME = "ros2_monitor_graph_discovery"
SYSTEM_TOPICS = {"/parameter_events", "/rosout"}
PARAMETER_SERVICE_SUFFIXES = {
    "describe_parameters",
    "get_parameter_types",
    "get_parameters",
    "get_type_description",
    "list_parameters",
    "set_parameters",
    "set_parameters_atomically",
}


def _is_parameter_service(name: str) -> bool:
    return name.rsplit("/", 1)[-1] in PARAMETER_SERVICE_SUFFIXES


def _is_action_hidden_name(name: str) -> bool:
    return "/_action/" in name


def _is_service_event_topic(name: str) -> bool:
    return name.endswith("/_service_event")


def parse_action_list_t(output: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in output.splitlines():
        match = re.match(r"^\s*(?P<name>\S+)\s+\[(?P<interface>[^\]]+)\]\s*$", line)
        if match:
            rows.append(
                {
                    "name": match.group("name"),
                    "interface": match.group("interface"),
                    "source_kind": "action",
                }
            )
    return sorted(rows, key=lambda row: row["name"])


def discover_actions_with_cli() -> list[dict[str, str]]:
    completed = subprocess.run(
        ["ros2", "action", "list", "-t"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        timeout=5,
        check=False,
    )
    if completed.returncode != 0:
        return []
    return parse_action_list_t(completed.stdout)


def filter_graph(
    graph: dict[str, list[dict[str, str]]],
    *,
    include_system: bool = False,
) -> dict[str, list[dict[str, str]]]:
    """Remove ROS 2 infrastructure resources from the default showcase view."""
    if include_system:
        return graph
    return {
        "topics": [
            row for row in graph.get("topics", [])
            if row.get("name") not in SYSTEM_TOPICS
            and not _is_action_hidden_name(str(row.get("name", "")))
            and not _is_service_event_topic(str(row.get("name", "")))
        ],
        "services": [
            row for row in graph.get("services", [])
            if not str(row.get("name", "")).startswith(f"/{DISCOVERY_NODE_NAME}/")
            and not _is_parameter_service(str(row.get("name", "")))
            and not _is_action_hidden_name(str(row.get("name", "")))
        ],
        "actions": list(graph.get("actions", [])),
    }


class GraphDiscovery:
    def __init__(self) -> None:
        from rclpy.node import Node

        class _Node(Node):
            pass

        self._node = _Node(DISCOVERY_NODE_NAME)

    def snapshot(self) -> dict[str, list[dict[str, str]]]:
        time.sleep(1.0)
        topics = [
            {"name": name, "interface": types[0], "source_kind": "topic"}
            for name, types in self._node.get_topic_names_and_types()
            if types
        ]
        services = [
            {"name": name, "interface": types[0], "source_kind": "service"}
            for name, types in self._node.get_service_names_and_types()
            if types
        ]
        actions: list[dict[str, str]] = []
        try:
            action_rows = self._node.get_action_names_and_types()
        except AttributeError:
            action_rows = []
        for name, types in action_rows:
            if types:
                actions.append(
                    {"name": name, "interface": types[0], "source_kind": "action"}
                )
        if not actions:
            actions = discover_actions_with_cli()
        return {
            "topics": sorted(topics, key=lambda row: row["name"]),
            "services": sorted(services, key=lambda row: row["name"]),
            "actions": sorted(actions, key=lambda row: row["name"]),
        }

    def destroy_node(self) -> None:
        self._node.destroy_node()


def discover(*, include_system: bool = False) -> dict[str, Any]:
    import rclpy

    rclpy.init(args=None)
    node = GraphDiscovery()
    try:
        return filter_graph(node.snapshot(), include_system=include_system)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover visible ROS 2 graph resources.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument(
        "--include-system",
        action="store_true",
        help="Include /rosout, /parameter_events, and parameter services.",
    )
    args = parser.parse_args()
    graph = discover(include_system=args.include_system)
    if args.json:
        print(json.dumps(graph, ensure_ascii=False))
        return 0
    for key in ("topics", "services", "actions"):
        print(f"\n{key.title()}")
        for row in graph[key]:
            print(f"  {row['name']:<45} {row['interface']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
