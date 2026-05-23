# Deployment Documentation Package

This directory contains the deliverables prepared for the promotion slide:

| File | Purpose |
|---|---|
| `related_work_survey.md` | Literature survey of how related ROS / ROS 2 runtime-verification works depict the deployment of their monitoring components. |
| `capability_comparison.md` | Capability-level comparison between this project and 12 related works. |
| `config_to_deployment.md` | Specification mapping each Monitor config shape to the resulting deployment topology (final-form, not just code-current). |
| `deployment_diagram.puml` | UML 2.x deployment diagram (PlantUML source) for the final-form ROS2-Monitor-Infra deployment. |
| `deployment_diagram.png` / `.svg` | Rendered deployment diagram, slide-ready. |
| `promotion_slide.puml` | Integrated diagram combining the existing architecture view with the new deployment view. |
| `promotion_slide.png` / `.svg` | Rendered integrated diagram, slide-ready. |

All artifacts target an academic audience and use standard UML 2.x deployment notation (`«device»`, `«executionEnvironment»`, `«artifact»`, `«deploy»`).

Components that are not yet implemented in the current codebase but belong to the final-form architecture are marked with the stereotype `«planned»` so the diagram is honest about scope.
