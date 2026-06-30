# ROS2-Monitor-Infra Documentation

## Normative References

| Question | Document |
|---|---|
| What fields and values can runtime YAML contain? | [config_spec.md](config_spec.md) |
| Which concrete configuration files exist, and what was missing before the documentation audit? | [config_inventory.md](config_inventory.md) |
| How is a new DSL adapted? | [dsl_adaptation_guide.md](dsl_adaptation_guide.md) |
| How can runtime configuration be generated rather than handwritten? | [config_generation_algorithm.tex](config_generation_algorithm.tex) (algorithm); `monitor/config_gen.py` + [demo/config_gen/](../demo/config_gen/) (implementation) |
| What is the stable `DataRecord` representation? | [datarecord_spec.md](datarecord_spec.md) |
| What is the converter→verdict DSL record contract (and split-transport wire format)? | [dsl_record_spec.md](dsl_record_spec.md) |

## Supporting Material

| Topic | Document |
|---|---|
| DSL-layer history, design decisions, and future TODOs | [dsl_extension_todos.md](dsl_extension_todos.md) |
| Deployment demo validation | [DEPLOYMENT_TEST_REPORT.md](DEPLOYMENT_TEST_REPORT.md) |
| Runtime sequence diagrams | [sequence_diagrams/](sequence_diagrams/) |

The runtime YAML reference and DSL adaptation guide describe implemented
behavior. The core of the generation algorithm — projecting a deployment JSON
request (hosts / runtimes / links) into runtime YAML — is implemented in
`monitor/config_gen.py`, with worked examples and behaviour-equivalence tests
under [demo/config_gen/](../demo/config_gen/). The LaTeX generation algorithm
still describes the broader intended design; the remaining prerequisite (a
machine-readable per-`custom/` plugin manifest, so plugin class paths and
constructor arguments can be discovered automatically rather than written into
each request) is not yet implemented.
