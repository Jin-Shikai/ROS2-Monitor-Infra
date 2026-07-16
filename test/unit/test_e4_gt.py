import json

from eval.e4.check_gt import physical_goal_checks


def write_mission(path, result="SUCCEEDED"):
    path.write_text(json.dumps({"events": [
        {
            "type": "goal_sent",
            "leg": "1",
            "robot": "robot1",
            "t": 10.0,
            "pose": [2.5, 0.0, 0.0],
        },
        {
            "type": "goal_result",
            "leg": "1",
            "robot": "robot1",
            "t": 12.0,
            "result": result,
        },
    ]}))


def test_physical_goal_check_accepts_reached_gazebo_pose(tmp_path):
    mission = tmp_path / "mission.json"
    write_mission(mission)
    rows = [(12.01, 2.45, 0.02, -2.0, -0.5, 4.0)]

    checks, ok = physical_goal_checks(rows, str(mission), tolerance=0.5)

    assert ok
    assert checks[0]["ok"]
    assert checks[0]["position_error_m"] < 0.1


def test_physical_goal_check_rejects_false_nav2_success(tmp_path):
    mission = tmp_path / "mission.json"
    write_mission(mission)
    rows = [(12.01, -0.2, 0.0, -2.0, -0.5, 1.0)]

    checks, ok = physical_goal_checks(rows, str(mission), tolerance=0.5)

    assert not ok
    assert not checks[0]["ok"]
    assert checks[0]["result"] == "SUCCEEDED"
    assert checks[0]["position_error_m"] == 2.7
