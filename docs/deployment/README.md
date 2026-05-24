# Deployment Documentation Package

This directory contains the deliverables prepared for the promotion slide.

| File | Purpose |
|---|---|
| `paper_summaries.md` | Per-paper structured technical summaries built by reading the seven PDFs end-to-end. Identity · contributions · architecture · DSL · data path · verdict · feedback · evaluation · maturity · limitations · quotes. |
| `capability_comparison.md` | Multi-axis comparison (functionality · implementation · features) of this project against the seven first-hand reviewed systems plus four secondary references. Includes an "advantages" section and an honest "where we are weaker" section. |
| `related_work_survey.md` | Literature survey of 12 related works with citations, figure-type analysis, and cross-cutting patterns. Citations for entries 1–8 and 10 have been verified against the PDFs; entries 9, 11, 12 remain abstract-level (flagged inline). |
| `config_to_deployment.md` | Specification mapping each Monitor config shape to the resulting deployment topology (7 deltas + 5 presets P1–P5). |
| `deployment_diagram.dot` / `.png` / `.svg` | UML 2.x deployment diagram (Graphviz source + rendered output), slide-ready. Reflects the **Final Vision** topology with extension-interface lollipops marking the plugin SPI. |
| `promotion_slide.dot` / `.png` / `.svg` | Integrated diagram combining the architectural view (Specification & Plugins + Runtime Verification Pipeline) with the new deployment view, linked by «deploy» arrows. |

All artifacts target an academic audience and use standard UML 2.x deployment notation (`«device»`, `«executionEnvironment»`, `«artifact»`, `«deploy»`), plus **provided-interface lollipops** for the plugin SPI (DataConverter, VerdictService, Exporter\<T\>, TransportAdapter, Transformer, FeedbackCommand).

The deployment diagram shows the **Final Vision** topology. Components designed-for but not yet implemented in the current codebase (Feedback Runtime, Evidence Runtime stack) are part of the vision; their implementation status is tracked in `config_to_deployment.md` and `capability_comparison.md`.

## Rendering

```
dot -Tpng deployment_diagram.dot -o deployment_diagram.png
dot -Tsvg deployment_diagram.dot -o deployment_diagram.svg
dot -Tpng promotion_slide.dot   -o promotion_slide.png
dot -Tsvg promotion_slide.dot   -o promotion_slide.svg
```

Requires Graphviz (`apt install graphviz`). PlantUML versions of these diagrams were dropped because PlantUML's layout engine could not produce slide-quality output for this many cross-cluster edges; Graphviz `dot` with `compound=true` and explicit `rank=same` chains gives proper UML deployment layout.

## Reading order
1. `paper_summaries.md` — what each related framework actually does.
2. `capability_comparison.md` — how this project compares on functionality / implementation / features.
3. `related_work_survey.md` — broader context (12 papers) and deployment-figure patterns.
4. `config_to_deployment.md` — the configuration semantics that drive the deployment diagram.
5. `deployment_diagram.png` and `promotion_slide.png` — slide-ready figures.
