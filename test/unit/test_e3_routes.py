import pytest

from eval.e3.check_routes import analyze, crossing_y_values


def test_crossing_interpolates_gate_y():
    rows = [(1.0, 1.2, -1.0), (2.0, 1.6, -1.4)]
    assert crossing_y_values(rows, 1.0, 2.0, 1.4) == pytest.approx([-1.2])


def test_expected_lower_upper_blocked_sequence_passes():
    rows = [
        (1.0, 1.2, -1.2), (2.0, 1.6, -1.3),
        (3.0, 1.6, 1.3), (4.0, 1.2, 1.2),
        (5.0, -2.0, -0.5), (6.0, 0.5, 0.0),
    ]
    events = [
        {"type": "goal_sent", "goal": "A", "t": 1.0},
        {"type": "goal_result", "goal": "A", "t": 2.0, "result": "SUCCEEDED"},
        {"type": "goal_sent", "goal": "B", "t": 3.0},
        {"type": "goal_result", "goal": "B", "t": 4.0, "result": "SUCCEEDED"},
        {"type": "goal_sent", "goal": "C", "t": 5.0},
        {"type": "goal_result", "goal": "C", "t": 6.0, "result": "CANCELED"},
    ]
    _goals, checks, ok = analyze(rows, events)
    assert ok
    assert checks == {
        "goal_a_uses_lower_baseline": True,
        "goal_b_forced_to_upper": True,
        "goal_c_did_not_cross_closed_partition": True,
    }


def test_unchanged_lower_route_is_rejected():
    rows = [
        (1.0, 1.2, -1.2), (2.0, 1.6, -1.3),
        (3.0, 1.6, -1.3), (4.0, 1.2, -1.2),
    ]
    events = [
        {"type": "goal_sent", "goal": "A", "t": 1.0},
        {"type": "goal_result", "goal": "A", "t": 2.0, "result": "SUCCEEDED"},
        {"type": "goal_sent", "goal": "B", "t": 3.0},
        {"type": "goal_result", "goal": "B", "t": 4.0, "result": "SUCCEEDED"},
    ]
    _goals, checks, ok = analyze(rows, events)
    assert not ok
    assert not checks["goal_b_forced_to_upper"]
