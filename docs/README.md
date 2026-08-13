# ROS2-Monitor-Infra Documentation

## Normative References

| Question | Document |
|---|---|
| What fields and values can runtime YAML contain? | [config_spec.md](config_spec.md) |
| How is a new DSL adapted? | [dsl_adaptation_guide.md](dsl_adaptation_guide.md) |
| How can runtime configuration be generated rather than handwritten? | [config_generation_algorithm.tex](config_generation_algorithm.tex) (algorithm); `monitor/config_gen.py` (implementation) |
| What is the stable `DataRecord` representation? | [datarecord_spec.md](datarecord_spec.md) |
| What is the converter→verdict DSL record contract (and dsl-endpoint wire format)? | [dsl_record_spec.md](dsl_record_spec.md) |

## Supporting Material

| Topic | Document |
|---|---|
| Runtime sequence diagrams | [sequence_diagrams/](sequence_diagrams/) |

The runtime YAML reference and DSL adaptation guide describe implemented
behavior. The core of the generation algorithm — projecting a deployment JSON
request (hosts / runtimes / links) into runtime YAML — is implemented in
`monitor/config_gen.py`. The dashboard reads
machine-readable plugin manifests from `custom/manifests/` so common plugin
class paths and constructor arguments can be surfaced as typed UI fields.
