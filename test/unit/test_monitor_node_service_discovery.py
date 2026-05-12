"""Unit tests for MonitorNode._register_service auto-discovery behavior.

Verifies that the service `type` field can be omitted from config when the
service is already active on the ROS2 network: in that case the type is
resolved via `_active_service_types`. Falls back to an explicit error log
when neither source provides a type.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import monitor_node
from monitor_node import MonitorNode


class _FakeLogger:
    def __init__(self):
        self.errors: list[str] = []
        self.infos: list[str] = []

    def error(self, msg): self.errors.append(msg)
    def info(self, msg): self.infos.append(msg)
    def warn(self, msg): pass


def _make_node(active_service_types: dict[str, str]) -> MonitorNode:
    """Build a MonitorNode without invoking rclpy / Node.__init__."""
    node = MonitorNode.__new__(MonitorNode)
    node.session_id = "sid"
    node.config = MagicMock()
    node.config.output_dir = "."
    node.dispatcher = MagicMock()
    node._converter_dispatcher = MagicMock()
    node._source_dispatchers = []
    node.manager = MagicMock()
    node._active_service_types = active_service_types
    node._logger = _FakeLogger()
    node.get_logger = lambda: node._logger  # type: ignore[method-assign]
    return node


@patch.object(monitor_node, "ServiceCollector")
def test_service_type_from_config_takes_precedence(mock_collector):
    node = _make_node(active_service_types={"/svc": "discovered/srv/Type"})

    node._register_service({"name": "/svc", "type": "explicit/srv/Type"})

    mock_collector.assert_called_once()
    kwargs = mock_collector.call_args.kwargs
    assert kwargs["service_type_str"] == "explicit/srv/Type"
    node.manager.register.assert_called_once()
    assert node._logger.errors == []


@patch.object(monitor_node, "ServiceCollector")
def test_service_type_auto_discovered_when_missing(mock_collector):
    node = _make_node(active_service_types={"/set_bool": "std_srvs/srv/SetBool"})

    node._register_service({"name": "/set_bool"})

    mock_collector.assert_called_once()
    kwargs = mock_collector.call_args.kwargs
    assert kwargs["service_type_str"] == "std_srvs/srv/SetBool"
    node.manager.register.assert_called_once()
    assert node._logger.errors == []


@patch.object(monitor_node, "ServiceCollector")
def test_service_skipped_when_type_unknown(mock_collector):
    node = _make_node(active_service_types={})

    node._register_service({"name": "/missing"})

    mock_collector.assert_not_called()
    node.manager.register.assert_not_called()
    assert len(node._logger.errors) == 1
    assert "/missing" in node._logger.errors[0]


@patch.object(monitor_node, "ServiceCollector")
def test_service_skipped_when_name_missing(mock_collector):
    node = _make_node(active_service_types={"/svc": "std_srvs/srv/SetBool"})

    node._register_service({"type": "std_srvs/srv/SetBool"})

    mock_collector.assert_not_called()
    node.manager.register.assert_not_called()
    assert len(node._logger.errors) == 1
