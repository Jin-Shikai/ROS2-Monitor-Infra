from eval.e3.check_physical_poses import check_events


def test_initial_and_successful_goals_match_gazebo():
    rows = [
        (10.0, -2.02, -0.49),
        (20.0, 2.45, 0.03),
        (30.0, -1.96, -0.52),
    ]
    events = [
        {"type": "initial_pose", "t": 10.0, "pose": [-2.0, -0.5, 0.0]},
        {"type": "goal_sent", "goal": "A", "t": 11.0, "pose": [2.5, 0.0, 0.0]},
        {"type": "goal_result", "goal": "A", "t": 20.0, "result": "SUCCEEDED"},
        {"type": "goal_sent", "goal": "B", "t": 21.0, "pose": [-2.0, -0.5, 3.14]},
        {"type": "goal_result", "goal": "B", "t": 30.0, "result": "SUCCEEDED"},
    ]

    checks, ok = check_events(rows, events, tolerance=0.2)

    assert ok
    assert [check["target"] for check in checks] == ["initial", "A", "B"]


def test_amcl_false_success_is_rejected_by_gazebo_pose():
    rows = [(10.0, -2.0, -0.5), (20.0, 0.4, 0.0)]
    events = [
        {"type": "initial_pose", "t": 10.0, "pose": [-2.0, -0.5, 0.0]},
        {"type": "goal_sent", "goal": "A", "t": 11.0, "pose": [2.5, 0.0, 0.0]},
        {"type": "goal_result", "goal": "A", "t": 20.0, "result": "SUCCEEDED"},
    ]

    checks, ok = check_events(rows, events, tolerance=0.5)

    assert not ok
    assert checks[-1]["target"] == "A"
    assert checks[-1]["position_error_m"] == 2.1
    assert not checks[-1]["ok"]


def test_failed_goal_does_not_claim_a_physical_endpoint():
    rows = [(10.0, -2.0, -0.5), (20.0, 0.0, 0.0)]
    events = [
        {"type": "initial_pose", "t": 10.0, "pose": [-2.0, -0.5, 0.0]},
        {"type": "goal_sent", "goal": "C", "t": 11.0, "pose": [2.5, 0.0, 0.0]},
        {"type": "goal_result", "goal": "C", "t": 20.0, "result": "CANCELED"},
    ]

    checks, ok = check_events(rows, events, tolerance=0.5)

    assert ok
    assert [check["target"] for check in checks] == ["initial"]
