# Custom Plugins

Converter and verdict-service plugins shipped with the project.

| File | Used by |
|---|---|
| `speed.py` + `threshold.py` | speed check preset (dashboard, E1–E3) |
| `relative_speed.py` + `threshold.py` | two-robot relative speed preset |
| `reset_pose_effect.py` | reset service effect preset |
| `nav_goal.py` | Nav2 goal-deadline supervision (E3) |
| `separation_converter.py` + `separation_verdict.py` | fleet minimum-separation property (E4, E5) |

Manifest JSON files in `manifests/` define the dashboard-facing business
parameters.
