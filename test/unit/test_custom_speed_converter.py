from custom.speed import CmdVelSpeedConverter
from data_record import DataRecord


def _record(data=None):
    return DataRecord.from_topic_msg(
        session_id="sid",
        topic_name="/cmd_vel",
        msg_type="geometry_msgs/msg/Twist",
        data=data or {"linear": {"x": 0.7}},
        seq=1,
    )


def test_projects_command_speed():
    out = CmdVelSpeedConverter().convert(_record())
    assert out is not None
    assert out["speed"] == 0.7
    assert out["_property_id"] == "speed_check"
    assert out["_source_name"] == "/cmd_vel"
    assert out["_record_id"] == "sid:topic:/cmd_vel:-:1"


def test_reads_flat_extractor_output():
    out = CmdVelSpeedConverter().convert(_record({"linear.x": 0.4}))
    assert out is not None
    assert out["speed"] == 0.4


def test_drops_records_without_speed():
    assert CmdVelSpeedConverter().convert(_record({"angular": {"z": 1.0}})) is None
