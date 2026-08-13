import math

from converter import DataConverter

class SeparationDistanceConverter(DataConverter):
    name = "SeparationDistanceConverter"

    def __init__(self, robot_a="/robot1", robot_b="/robot2",
                 topic_suffix="/amcl_pose", property_id="fleet_separation"):
        self.robots = (robot_a.rstrip("/"), robot_b.rstrip("/"))
        self.topic_suffix = topic_suffix
        self.property_id = property_id
        self.latest = {}

    def convert(self, record):
        data = record.data
        if "pose.pose.position.x" in data:
            xy = [float(data["pose.pose.position.x"]),
                  float(data["pose.pose.position.y"])]
        else:
            position = data["pose"]["pose"]["position"]
            xy = [float(position["x"]), float(position["y"])]
        robot = record.source_name[: -len(self.topic_suffix)]
        self.latest[robot] = (xy, record.record_id, record.timestamp)
        if not all(r in self.latest for r in self.robots):
            return None
        (pa, id_a, ts_a), (pb, id_b, ts_b) = (self.latest[r] for r in self.robots)
        return {
            "separation_m": math.hypot(pa[0] - pb[0], pa[1] - pb[1]),
            "positions": {self.robots[0]: pa, self.robots[1]: pb},
            "_property_id": self.property_id,
            "_timestamp": max(ts_a, ts_b),
            "_input_record_ids": [id_a, id_b],
            "_source_name": "fleet",
        }
