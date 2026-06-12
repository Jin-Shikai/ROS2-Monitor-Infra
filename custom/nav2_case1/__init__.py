"""Nav2 case study 1 — `/cmd_vel` speed-limit property.

One property per package. The converter and verdict each live in their
own module so the package layout reads like an outline of the property
itself: "data shape" + "judgement logic".

Wire-up (see demo/nav2_compatible_local/full_nav2_config.yaml):

    converters:
      - type: custom.nav2_case1.cmd_vel_speed_converter:CmdVelSpeedConverter
        verdict:
          type: custom.nav2_case1.cmd_vel_speed_verdict:CmdVelSpeedVerdict
          exporters:
            - type: file
              path: verdicts_{session_id}.jsonl
"""
