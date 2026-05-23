# Deployment Documentation Package

This directory contains the deliverables prepared for the promotion slide.

| File | Purpose |
|---|---|
| `paper_summaries.md` | Per-paper structured technical summaries built by reading the seven PDFs end-to-end. Identity · contributions · architecture · DSL · data path · verdict · feedback · evaluation · maturity · limitations · quotes. |
| `capability_comparison.md` | Multi-axis comparison (functionality · implementation · features) of this project against the seven first-hand reviewed systems plus four secondary references. Includes an "advantages" section and an honest "where we are weaker" section. |
| `related_work_survey.md` | Literature survey of 12 related works with citations, figure-type analysis, and cross-cutting patterns. Citations for entries 1–8 and 10 have been verified against the PDFs; entries 9, 11, 12 remain abstract-level (flagged inline). |
| `config_to_deployment.md` | Specification mapping each Monitor config shape to the resulting deployment topology (7 deltas + 5 presets P1–P5). |
| `deployment_diagram.puml` / `.png` / `.svg` | UML 2.x deployment diagram (PlantUML source + rendered output), slide-ready. |
| `promotion_slide.puml` / `.png` / `.svg` | Integrated diagram combining the existing architecture view with the new deployment view. |

All artifacts target an academic audience and use standard UML 2.x deployment notation (`«device»`, `«executionEnvironment»`, `«artifact»`, `«deploy»`).

Components designed-for but not yet implemented in the current codebase are marked with the stereotype `«planned»` so the diagram is honest about scope.

## Reading order
1. `paper_summaries.md` — what each related framework actually does.
2. `capability_comparison.md` — how this project compares on functionality / implementation / features.
3. `related_work_survey.md` — broader context (12 papers) and deployment-figure patterns.
4. `config_to_deployment.md` — the configuration semantics that drive the deployment diagram.
5. `deployment_diagram.png` and `promotion_slide.png` — slide-ready figures.
