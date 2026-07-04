# Config generation demos

These JSON files are *generation requests* in the deployment model from
`Thesis/Pseudocode/pseudocode.tex`: physical `hosts` own executable `runtimes`
(`ros2` / `monitor` / `converter` / `verdict_service`), and `links` describe how
runtimes on different hosts exchange `records` or `dsl` payloads.
`monitor/config_gen.py` projects a request into the runtime YAML the existing
entrypoints already consume — it adds no new runtime code.

Both converter kinds are plain `Converter` plugins (same `class_path`
mechanism); they differ only in **output type**, which is what decides who they
can feed:

- a `dsl_converter` returns a dict (dsl payload) → feeds a **verdict**, in
  process or over a dsl transport endpoint;
- a `data_filter` returns a `DataRecord` (records payload) → can feed **another
  converter**, in process via a `converter -> converter` link or across hosts
  over the ordinary DataRecord transport.

Demo plugins: `custom/speed_aggregate_filter.py:SpeedAggregateFilter`
(dsl_converter — speed dict → verdict), `custom/odom_speed_filter.py:OdomSpeedFilter`
(data_filter — speed `DataRecord` → next converter), and
`custom/relative_speed.py:RelativeSpeedConverter` (stateful join of two robots).

## Files

| Request | Topology | Projects to |
|---|---|---|
| `all_in_one.json` | one host: ros2 + monitor + dsl_converter + verdict | one `monitor_node` YAML (behaviour of `deploy_mode1`) |
| `three_host.json` | robot monitor → dsl_converter host → verdict host | three YAMLs joined by an MQTT dsl seam (behaviour of `deploy_split_converter_verdict`) |
| `converter_chain.json` | robot monitor → data_filter host → dsl_converter+verdict host | three YAMLs; the converter→converter seam is a DataRecord MQTT namespace |
| `file_transport.json` | robot monitor → verifier (converter+verdict), `records` link over **file** | two YAMLs joined by a shared JSONL file the verifier tails (`follow: true`) |
| `two_robot_fleet.json` | two robot monitors → converter host (relative speed join) → verdict host (`> 0.5` check) | four YAMLs; the two same-broker records links merge into one input on the converter host |

## Transport kinds

A `Link.transport.kind` is only materialised for **cross-host** links —
co-located runtimes run in one process, so a same-host deployment needs no
transport at all (its `kind` is irrelevant). Cross-host `records` and `dsl`
links both support `mqtt` and `file`; the file carrier is a shared link-scoped
JSONL path that the consuming side tails live (`follow: true`).

Hosts are not restricted to one role: a single host may mix converters and
verdict services with any combination of inbound and outbound links — the
generator emits one `node_runner` YAML with the corresponding `inputs:`,
`outputs:`, and `links:` sections. Multiple inbound links are all honoured;
links that share a transport namespace are merged into one input.

## Generate

```bash
python monitor/config_gen.py demo/config_gen/three_host.json -o ./generated
```

This writes one `<host>.yaml` per running host and prints the command to launch
each. `ros2`-only hosts produce no file (they only supply source definitions).

## Equivalence test

`test/unit/test_config_gen.py` projects the requests and drives records through
the *same* graph builders the real entrypoints use, asserting the generated
YAML is behaviour-equivalent to the hand-written demos (no ROS2 required).
