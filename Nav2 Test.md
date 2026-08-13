# Nav2 Test

## 1. Nav2 without monitor

![image-20260506232352318](/home/shikai/.config/Typora/typora-user-images/image-20260506232352318.png)

## 2. config_nav2.yaml

```yaml
monitor:
  output_dir: ./output/nav2
topics:
  - name: /odom
    transformers:
      - type: FieldExtractor
        fields:
          - pose.pose.position.x
          - pose.pose.position.y
          - twist.twist.linear.x
          - twist.twist.angular.z
      - type: RateThrottler
        max_rate_hz: 5.0

  - name: /amcl_pose
    transformers:
      - type: FieldExtractor
        fields:
          - pose.pose.position.x
          - pose.pose.position.y
          - pose.covariance

  - name: /cmd_vel
    transformers:
      - type: FieldExtractor
        fields:
          - twist.linear.x 
          - twist.linear.y
          - twist.angular.z
      - type: RateThrottler
        max_rate_hz: 5.0

  - name: /plan
    transformers:
      - type: OnChangeFilter
        watch_fields:
          - header.stamp.sec
          - header.stamp.nanosec
          
actions:
  - name: /navigate_to_pose
    type: nav2_msgs/action/NavigateToPose
    phases: [feedback, status]
    transformers:
      - type: FieldExtractor
        fields:
          - feedback.distance_remaining
          - feedback.number_of_recoveries
          - feedback.navigation_time.sec
          - feedback.estimated_time_remaining.sec
          - feedback.current_pose.pose.position.x
          - feedback.current_pose.pose.position.y
          - status_list
      - type: RateThrottler
        max_rate_hz: 2.0

exporters:
  - type: file

converters:
  - type: custom.rule_based:RuleBasedConverter
    source_match: "^/cmd_vel$"
    field_map:
      speed: twist.linear.x
    property_id: cmd_vel_speed_limit
    verdict:
      type: custom.threshold:ThresholdVerdict
      property_id: cmd_vel_speed_limit
      field: speed
      op: ">"
      threshold: 0.30
      sustain_sec: 0.0
      output: verdicts_{session_id}.jsonl

```

## 3. custom/verdict.py

```python
import operator
from verdict import Verdict, VerdictService

_OPS = {
    ">": operator.gt
}

class ThresholdVerdict(VerdictService):
    name = "ThresholdVerdict"

    def __init__(
        self,
        property_id: str,
        field: str,
        op: str,
        threshold: float,
        sustain_sec: float = 0.0,
    ):
        self.property_id = property_id
        self.field = field
        self.op = op
        self._cmp = _OPS[op]
        self.threshold = float(threshold)

    def evaluate(self, dsl_record: Any) -> Verdict | None:
        import time
        if not isinstance(dsl_record, dict) or self.field not in dsl_record:
            return None
        value = dsl_record[self.field]
        ts = dsl_record.get("_timestamp", time.time())
        breached = self._cmp(value, self.threshold)

        if breached:
            if self._breach_started_at is None:
                self._breach_started_at = ts
            duration = ts - self._breach_started_at
            if not self._fired and duration >= self.sustain_sec:
                self._fired = True
                return Verdict(
                    timestamp=ts,
                    property_id=self.property_id,
                    result=False,
                    details={
                        "field": self.field,
                        "op": self.op,
                        "threshold": self.threshold,
                        "value": value,
                        "duration_sec": duration,
                    },
                )
            return None

        if self._fired:
            self._fired = False
            self._breach_started_at = None
            return Verdict(
                timestamp=ts,
                property_id=self.property_id,
                result=True,
                details={
                    "field": self.field,
                    "value": value,
                    "note": "breach cleared",
                },
            )
        self._breach_started_at = None
        return None

```

## 4. Result

### Monitor

### Verdict

{"timestamp": 1778111148.9588788, "property_id": "cmd_vel_speed_limit", "result": false, "details": {"field": "speed", "op": ">", "threshold": 0.3, "value": 0.34524041414260864, "duration_sec": 0.0}}

{"timestamp": 1778111152.2983212, "property_id": "cmd_vel_speed_limit", "result": true, "details": {"field": "speed", "value": 0.28726768493652344, "note": "breach cleared"}}

## 5. Plot

![image-20260507021026785](/home/shikai/.config/Typora/typora-user-images/image-20260507021026785.png)
