# DataRecord Specification

> Version: 1.1 — 2026-04-15 (added `source_node`)
> Implementation: `monitor/data_record.py`
> Example fixture: `output/example_fixture.jsonl`

## Overview

A **DataRecord** is the universal data unit in the monitoring pipeline. Every
captured ROS2 message — whether from a topic subscription, a service
introspection event, or an action feedback — is wrapped into a DataRecord
before entering the TransformerPipeline, and remains a DataRecord when
exported to Exporters.

Records are serialized as **JSONL** (one JSON object per line). Empty fields
(`null`, `""`, `{}`) are stripped from the serialized output to keep lines
compact.

---

## Field Reference

### `_type`

| | |
|---|---|
| **Type** | `string` |
| **Required** | Always |
| **Purpose** | Top-level discriminator for the JSONL record kind. Readers should switch on this field first. |

| Value | Meaning |
|---|---|
| `"session_start"` | First record in a monitoring session. `data` contains the active configuration. |
| `"data"` | A captured ROS2 message. All source identity and payload fields are populated. |
| `"session_end"` | Last record in a session. `data` contains aggregated statistics. |
| `"error"` | An error event logged by the framework (e.g. serialization failure, subscription lost). |

---

### `session_id`
| | |
|---|---|
| **Type** | `string` |
| **Required** | Always |
| **Format** | `YYYYMMDD_HHMMSS_<8 hex chars>` (e.g. `"20260415_211500_a1b2c3d4"`) |
| **Purpose** | Uniquely identifies a monitoring session. Present on every record so that records from different sessions can be reliably distinguished even when written to the same file or MQTT topic. |

---

### `record_id`

| | |
|---|---|
| **Type** | `string` |
| **Required** | Only when `_type == "data"` |
| **Format** | `<session_id>:<source_type>:<source_name>:<phase-or->:<seq>` |
| **Example** | `"20260415_211500_a1b2c3d4:topic:/cmd_vel:-:7"` |
| **Purpose** | Stable identifier for one captured data record within a monitoring session. Verdict-producing converters should propagate this into DSL records as `_record_id` so Evidence services can link verdicts back to the exact input record(s). |

For topic records, the phase segment is `-`. For service and action records,
the phase segment is the DataRecord `phase` value, such as `request`,
`response`, `feedback`, or `status`.

---

### `source_type`

| | |
|---|---|
| **Type** | `string` |
| **Required** | Only when `_type == "data"` |
| **Purpose** | Identifies which ROS2 communication primitive produced this record. |

| Value | ROS2 Primitive | How data is collected |
|---|---|---|
| `"topic"` | Topic (pub/sub) | Direct `create_subscription()` on the topic. |
| `"service"` | Service (req/rep) | Subscribe to `/<service_name>/_service_event` hidden topic (requires introspection enabled). |
| `"action"` | Action (goal/feedback/result) | Subscribe to `/_action/feedback`, `/_action/status` hidden topics. Goal/result require service introspection. |

---

### `source_name`

| | |
|---|---|
| **Type** | `string` |
| **Required** | Only when `_type == "data"` |
| **Purpose** | The logical name of the monitored source in the ROS2 graph. |

| `source_type` | Example values |
|---|---|
| `"topic"` | `"/cmd_vel"`, `"/scan"`, `"/odom"`, `"/chatter"` |
| `"service"` | `"/set_bool"`, `"/map_server/load_map"` |
| `"action"` | `"/navigate_to_pose"`, `"/follow_waypoints"` |

> **Note**: This is the *logical* name (e.g. `"/navigate_to_pose"`), not the
> underlying hidden topic name (e.g. `"/navigate_to_pose/_action/feedback"`).
> The actual subscribed topic can be derived from `source_type` + `source_name` + `phase`.

---

### `source_node`

| | |
|---|---|
| **Type** | `array[string] \| null` |
| **Required** | Only when `_type == "data"` and the source node is known |
| **Purpose** | The ROS2 node name(s) that produced this record — the publisher (topic) or server (service/action). Absent if the node could not be resolved at collection time. |

| `source_type` | Typical value | Multiplicity |
|---|---|---|
| `"topic"` | `["fake_robot"]` | One entry per known publisher. Multiple entries if the topic has concurrent publishers (e.g. `["teleop_node", "nav2_controller"]`). |
| `"service"` | `["fake_robot"]` | Always one server per service name. |
| `"action"` | `["nav2_bt_navigator"]` | Always one server per action name. |

> **Node name format**: `"/namespace/node_name"` if namespaced, plain `"node_name"` if in the root namespace.
> This field is populated once at Collector initialization via `get_publishers_info_by_topic()`. It reflects the set of publishers at that moment; nodes that join or leave later are not tracked.

---

### `msg_type`

| | |
|---|---|
| **Type** | `string` |
| **Required** | Only when `_type == "data"` |
| **Format** | ROS2 type identifier: `<package>/msg/<Type>`, `<package>/srv/<Type>_Event`, or `<package>/action/<Type>_FeedbackMessage` |
| **Purpose** | Tells downstream converters the schema of the `data` field without requiring introspection of the content. |

| `source_type` | Example `msg_type` values |
|---|---|
| `"topic"` | `"std_msgs/msg/String"`, `"geometry_msgs/msg/Twist"`, `"sensor_msgs/msg/LaserScan"`, `"nav_msgs/msg/Odometry"` |
| `"service"` | `"std_srvs/srv/SetBool_Event"`, `"nav2_msgs/srv/LoadMap_Event"` |
| `"action"` (feedback) | `"nav2_msgs/action/NavigateToPose_FeedbackMessage"` |
| `"action"` (status) | `"action_msgs/msg/GoalStatusArray"` (fixed for all actions) |

---

### `phase`

| | |
|---|---|
| **Type** | `string \| null` |
| **Required** | Only when `_type == "data"` |
| **Purpose** | Disambiguates which part of a multi-step interaction (service or action) this record represents. |

| `source_type` | Possible `phase` values | Meaning |
|---|---|---|
| `"topic"` | `null` | Topics have no phases — each message is a complete unit. |
| `"service"` | `"request"` | A service request was sent or received. Derived from `event_type` 0 (REQUEST_SENT) or 1 (REQUEST_RECEIVED). |
| `"service"` | `"response"` | A service response was sent or received. Derived from `event_type` 2 (RESPONSE_SENT) or 3 (RESPONSE_RECEIVED). |
| `"action"` | `"feedback"` | Periodic progress update from the action server (subscribed via `/_action/feedback` hidden topic). |
| `"action"` | `"status"` | Goal state transitions (subscribed via `/_action/status` hidden topic). |
| `"action"` | `"goal"` | Goal submission event (requires service introspection on `/_action/send_goal`). |
| `"action"` | `"result"` | Final result retrieval (requires service introspection on `/_action/get_result`). |

> **Availability note**: `"feedback"` and `"status"` are always available
> (they are standard hidden topics). `"goal"` and `"result"` require that the
> action server node has service introspection enabled (e.g. Nav2 Kilted's
> `introspection_mode` parameter).

---

### `timestamp`

| | |
|---|---|
| **Type** | `float` |
| **Required** | Always |
| **Unit** | Seconds since Unix epoch (UTC), from `time.time()` |
| **Purpose** | Wall-clock time when the **monitor node** received/created this record. Used for cross-source time correlation and monitoring latency analysis. |

---

### `ros_timestamp`

| | |
|---|---|
| **Type** | `object \| null` |
| **Required** | Only when the original ROS2 message contains a meaningful `header.stamp` |
| **Format** | `{"sec": <int>, "nanosec": <int>}` |
| **Purpose** | The timestamp from the ROS2 message header, representing when the **source node** generated the data. The difference `timestamp - ros_timestamp` indicates monitoring pipeline latency. |

| Present | Absent |
|---|---|
| `sensor_msgs/msg/LaserScan` (has header) | `std_msgs/msg/String` (no header) |
| `nav_msgs/msg/Odometry` (has header) | `geometry_msgs/msg/Twist` (no header) |
| Service events (from `info.stamp`) | Action status (no meaningful stamp) |
| Action feedback (if inner msg has header) | — |

---

### `data`

| | |
|---|---|
| **Type** | `object` |
| **Required** | Always |
| **Purpose** | The primary payload. Content depends on `_type`. |

| `_type` | `data` contains |
|---|---|
| `"session_start"` | The monitoring configuration (parsed YAML). |
| `"data"` | The ROS2 message content as a dict (output of `message_to_ordereddict()`), possibly transformed by the pipeline. |
| `"session_end"` | Aggregated session statistics. |
| `"error"` | Error details (message, traceback, context). |

**For `_type == "data"`, the structure of `data` depends on `msg_type`:**

Before any Transformer is applied, `data` preserves the exact nested dict
structure of the ROS2 message (as produced by `rosidl_runtime_py.message_to_ordereddict()`).

After `FieldExtractor`, selected fields are flattened to **dot notation**:

```json
// Before FieldExtractor (raw Odometry):
{"pose": {"pose": {"position": {"x": 1.2, "y": 3.4}}}}

// After FieldExtractor (dot-notation):
{"pose.pose.position.x": 1.2, "pose.pose.position.y": 3.4}
```

**For `source_type == "service"`**, `data` contains only the unwrapped
request or response payload (extracted from the `_Event` wrapper):

```json
// Service request (SetBool):  data = request[0]
{"data": true}

// Service response (SetBool):  data = response[0]
{"success": true, "message": "OK"}
```

---

### `metadata`

| | |
|---|---|
| **Type** | `object` |
| **Required** | Only when `_type == "data"` (stripped when empty for other `_type` values) |
| **Purpose** | Framework-generated context about how this record was collected and processed. Not part of the monitored data itself. |

**Common keys (all `source_type` values):**

| Key | Type | Description |
|---|---|---|
| `seq` | `int` | Monotonically increasing sequence number per collector. Starts at 1 for each source. |
| `qos_profile` | `string` | QoS profile name used for the subscription (e.g. `"sensor_data"`, `"default"`). Added by the Collector. |
| `transformers_applied` | `list[string]` | Ordered list of Transformer class names that processed this record (e.g. `["RateThrottler", "FieldExtractor"]`). Added by TransformerPipeline. Empty list or absent if no transformers ran. |

**Additional keys for `source_type == "service"`:**

| Key | Type | Description |
|---|---|---|
| `event_type` | `int` | Raw event type from `ServiceEventInfo`. `0` = REQUEST_SENT, `1` = REQUEST_RECEIVED, `2` = RESPONSE_SENT, `3` = RESPONSE_RECEIVED. |
| `client_gid` | `list[int]` | 16-byte DDS Global ID of the service client. Can be used to correlate request/response pairs from the same caller. |
| `sequence_number` | `int` | Service call sequence number from `ServiceEventInfo`. Pairs a request with its corresponding response (same `sequence_number` value). |

**Additional keys for `source_type == "action"` (planned):**

| Key | Type | Description |
|---|---|---|
| `goal_id` | `list[int]` | 16-byte UUID of the action goal. Can be used to correlate feedback/status/goal/result records for the same goal. |

---

## Field Presence Matrix

The following table shows which fields are present in each combination of
`_type` and `source_type`:

| Field | `session_start` | `session_end` | `data` + `topic` | `data` + `service` | `data` + `action` | `error` |
|---|---|---|---|---|---|---|
| `_type` | yes | yes | yes | yes | yes | yes |
| `session_id` | yes | yes | yes | yes | yes | yes |
| `record_id` | — | — | yes | yes | yes | — |
| `source_type` | — | — | yes | yes | yes | — |
| `source_name` | — | — | yes | yes | yes | — |
| `source_node` | — | — | if known | if known | if known | — |
| `msg_type` | — | — | yes | yes | yes | — |
| `phase` | — | — | — | yes | yes | — |
| `timestamp` | yes | yes | yes | yes | yes | yes |
| `ros_timestamp` | — | — | if header | yes (from info.stamp) | if header in feedback | — |
| `data` | yes (config) | yes (stats) | yes (msg) | yes (req/resp) | yes (feedback/status) | yes (error) |
| `metadata` | — | — | yes | yes | yes | — |

> **"—"** means the field is absent from the serialized JSON (stripped by `to_json()`).

---

## Examples

### 1. Session Start

```json
{
  "_type": "session_start",
  "session_id": "20260415_211500_a1b2c3d4",
  "timestamp": 1776283880.630369,
  "data": {
    "monitor": {"output_dir": "./output"},
    "topics": [{"name": "/cmd_vel", "sample_rate_hz": 5.0}],
    "services": [{"name": "/set_bool"}]
  }
}
```

### 2. Topic — `std_msgs/msg/String` (no header, simplest case)

```json
{
  "_type": "data",
  "session_id": "20260415_211500_a1b2c3d4",
  "source_type": "topic",
  "source_name": "/chatter",
  "source_node": ["fake_robot"],
  "msg_type": "std_msgs/msg/String",
  "timestamp": 1776283880.6303737,
  "data": {"data": "Hello World: 42"},
  "metadata": {"seq": 1}
}
```

### 3. Topic — `geometry_msgs/msg/Twist` (no header, nested vectors)

```json
{
  "_type": "data",
  "session_id": "20260415_211500_a1b2c3d4",
  "source_type": "topic",
  "source_name": "/cmd_vel",
  "source_node": ["teleop_node", "nav2_controller"],
  "msg_type": "geometry_msgs/msg/Twist",
  "timestamp": 1776283880.6303775,
  "data": {
    "linear": {"x": 0.5, "y": 0.0, "z": 0.0},
    "angular": {"x": 0.0, "y": 0.0, "z": 0.3}
  },
  "metadata": {"seq": 2}
}
```

### 4. Topic — `sensor_msgs/msg/LaserScan` (has header, array fields)

```json
{
  "_type": "data",
  "session_id": "20260415_211500_a1b2c3d4",
  "source_type": "topic",
  "source_name": "/scan",
  "source_node": ["lidar_driver"],
  "msg_type": "sensor_msgs/msg/LaserScan",
  "timestamp": 1776283880.6303806,
  "ros_timestamp": {"sec": 1744742401, "nanosec": 500000000},
  "data": {
    "header": {"stamp": {"sec": 1744742401, "nanosec": 500000000}, "frame_id": "laser_frame"},
    "angle_min": -1.57,
    "angle_max": 1.57,
    "angle_increment": 0.01,
    "range_min": 0.1,
    "range_max": 10.0,
    "ranges": [1.2, 1.3, 1.1, 0.9, 1.5],
    "intensities": []
  },
  "metadata": {"seq": 3}
}
```

### 5. Topic — `nav_msgs/msg/Odometry` (has header, deeply nested, covariance arrays)

```json
{
  "_type": "data",
  "session_id": "20260415_211500_a1b2c3d4",
  "source_type": "topic",
  "source_name": "/odom",
  "source_node": ["diff_drive_controller"],
  "msg_type": "nav_msgs/msg/Odometry",
  "timestamp": 1776283880.6303842,
  "ros_timestamp": {"sec": 1744742401, "nanosec": 600000000},
  "data": {
    "header": {"stamp": {"sec": 1744742401, "nanosec": 600000000}, "frame_id": "odom"},
    "child_frame_id": "base_link",
    "pose": {
      "pose": {
        "position": {"x": 1.2, "y": 3.4, "z": 0.0},
        "orientation": {"x": 0.0, "y": 0.0, "z": 0.1, "w": 0.995}
      },
      "covariance": [0.01, 0.0, 0.0, "...(36 floats total)"]
    },
    "twist": {
      "twist": {
        "linear": {"x": 0.5, "y": 0.0, "z": 0.0},
        "angular": {"x": 0.0, "y": 0.0, "z": 0.1}
      },
      "covariance": [0.0, "...(36 floats total)"]
    }
  },
  "metadata": {"seq": 4}
}
```

### 6. Service — Request phase (`SetBool`)

```json
{
  "_type": "data",
  "session_id": "20260415_211500_a1b2c3d4",
  "source_type": "service",
  "source_name": "/set_bool",
  "source_node": ["fake_robot"],
  "msg_type": "std_srvs/srv/SetBool_Event",
  "phase": "request",
  "timestamp": 1776283880.6303897,
  "ros_timestamp": {"sec": 1744742402, "nanosec": 100000000},
  "data": {"data": true},
  "metadata": {
    "seq": 5,
    "event_type": 0,
    "client_gid": [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    "sequence_number": 1
  }
}
```

### 7. Service — Response phase (`SetBool`)

```json
{
  "_type": "data",
  "session_id": "20260415_211500_a1b2c3d4",
  "source_type": "service",
  "source_name": "/set_bool",
  "source_node": ["fake_robot"],
  "msg_type": "std_srvs/srv/SetBool_Event",
  "phase": "response",
  "timestamp": 1776283880.630393,
  "ros_timestamp": {"sec": 1744742402, "nanosec": 200000000},
  "data": {"success": true, "message": "OK"},
  "metadata": {
    "seq": 6,
    "event_type": 2,
    "client_gid": [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    "sequence_number": 1
  }
}
```

> **Correlating request ↔ response**: Match on `source_name` + `metadata.sequence_number`.
> The same `sequence_number` value appears in both the request and response
> records for a single service call. `client_gid` further distinguishes
> calls from different clients.

### 8. Action — Feedback (`NavigateToPose`)

```json
{
  "_type": "data",
  "session_id": "20260415_211500_a1b2c3d4",
  "source_type": "action",
  "source_name": "/navigate_to_pose",
  "source_node": ["nav2_bt_navigator"],
  "msg_type": "nav2_msgs/action/NavigateToPose_FeedbackMessage",
  "phase": "feedback",
  "timestamp": 1776283880.6303966,
  "data": {
    "goal_id": {"uuid": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]},
    "feedback": {
      "current_pose": {
        "header": {"stamp": {"sec": 1744742403, "nanosec": 0}, "frame_id": "map"},
        "pose": {
          "position": {"x": 2.1, "y": 4.5, "z": 0.0},
          "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}
        }
      },
      "distance_remaining": 3.2,
      "navigation_time": {"sec": 5, "nanosec": 0},
      "estimated_time_remaining": {"sec": 10, "nanosec": 0},
      "number_of_recoveries": 0
    }
  },
  "metadata": {"seq": 7}
}
```

### 9. Action — Status (`GoalStatusArray`)

```json
{
  "_type": "data",
  "session_id": "20260415_211500_a1b2c3d4",
  "source_type": "action",
  "source_name": "/navigate_to_pose",
  "source_node": ["nav2_bt_navigator"],
  "msg_type": "action_msgs/msg/GoalStatusArray",
  "phase": "status",
  "timestamp": 1776283880.630399,
  "data": {
    "status_list": [
      {
        "goal_info": {
          "goal_id": {"uuid": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]},
          "stamp": {"sec": 1744742400, "nanosec": 0}
        },
        "status": 2
      }
    ]
  },
  "metadata": {"seq": 8}
}
```

> **Goal status codes** (from `action_msgs/msg/GoalStatus`):
>
> | Value | Constant | Meaning |
> |---|---|---|
> | 0 | STATUS_UNKNOWN | Initial state |
> | 1 | STATUS_ACCEPTED | Goal accepted, awaiting execution |
> | 2 | STATUS_EXECUTING | Goal is currently being executed |
> | 3 | STATUS_CANCELING | Cancel requested, not yet completed |
> | 4 | STATUS_SUCCEEDED | Goal completed successfully |
> | 5 | STATUS_CANCELED | Goal was canceled |
> | 6 | STATUS_ABORTED | Goal was aborted by the server |

### 10. Session End

```json
{
  "_type": "session_end",
  "session_id": "20260415_211500_a1b2c3d4",
  "timestamp": 1776283880.6304016,
  "data": {
    "total_records": 8,
    "duration_sec": 10.5,
    "per_source": {
      "/chatter": {"received": 100, "sampled": 10}
    }
  }
}
```

---

## Service Event Unwrapping

Service introspection publishes `<SrvType>_Event` messages to the
`/<service_name>/_service_event` hidden topic. The raw event structure is:

```json
{
  "info": {
    "event_type": 0,
    "stamp": {"sec": 1744742402, "nanosec": 100000000},
    "client_gid": [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    "sequence_number": 1
  },
  "request": [{"data": true}],
  "response": []
}
```

The framework **unwraps** this into a DataRecord as follows:

| Raw event field | DataRecord field |
|---|---|
| `info.event_type` → 0,1 = request; 2,3 = response | `phase` |
| `info.stamp` | `ros_timestamp` |
| `info.event_type` | `metadata.event_type` |
| `info.client_gid` | `metadata.client_gid` |
| `info.sequence_number` | `metadata.sequence_number` |
| `request[0]` or `response[0]` (based on phase) | `data` |

The `event_type` integer encodes both direction and perspective:

| `event_type` | Constant | `phase` |
|---|---|---|
| 0 | REQUEST_SENT | `"request"` |
| 1 | REQUEST_RECEIVED | `"request"` |
| 2 | RESPONSE_SENT | `"response"` |
| 3 | RESPONSE_RECEIVED | `"response"` |

---

## Data After Transformation

When a TransformerPipeline is configured, the `data` field may differ from
the raw message. The `metadata.transformers_applied` list records which
transformers ran and in what order.

### FieldExtractor (dot notation)

Extracts specific fields and flattens keys using dot notation.

**Config:** `fields: ["pose.pose.position.x", "pose.pose.position.y", "twist.twist.linear.x"]`

**Before:**
```json
{
  "data": {
    "pose": {"pose": {"position": {"x": 1.2, "y": 3.4, "z": 0.0}, "orientation": {"x": 0.0, "y": 0.0, "z": 0.1, "w": 0.995}}, "covariance": [...]},
    "twist": {"twist": {"linear": {"x": 0.5, "y": 0.0, "z": 0.0}, "angular": {"x": 0.0, "y": 0.0, "z": 0.1}}, "covariance": [...]}
  },
  "metadata": {"seq": 4}
}
```

**After:**
```json
{
  "data": {
    "pose.pose.position.x": 1.2,
    "pose.pose.position.y": 3.4,
    "twist.twist.linear.x": 0.5
  },
  "metadata": {"seq": 4, "transformers_applied": ["FieldExtractor"]}
}
```

### RateThrottler

Drops records that arrive faster than the configured rate. Records that pass
through are unchanged; records that are dropped never reach the Exporter.

### OnChangeFilter

Only passes a record through when one or more of the watched fields have
changed compared to the previous record from the same source.
