from custom.fleet_distance import FleetDistanceConverter, MinimumFleetDistanceVerdict
from data_record import DataRecord


def _odom(name, x, y, seq):
    return DataRecord.from_topic_msg(
        "s", name, "nav_msgs/msg/Odometry",
        {"pose.pose.position.x": x, "pose.pose.position.y": y}, seq,
    )


def test_fleet_distance_global_predicate():
    converter = FleetDistanceConverter("/robot1", "/robot2")
    assert converter.convert(_odom("/robot1/odom", 0, 0, 1)) is None
    record = converter.convert(_odom("/robot2/odom", 0.5, 0, 2))
    assert record["distance"] == 0.5
    verdict = MinimumFleetDistanceVerdict(1.0).evaluate(record)
    assert verdict is not None
    assert verdict.result is False
