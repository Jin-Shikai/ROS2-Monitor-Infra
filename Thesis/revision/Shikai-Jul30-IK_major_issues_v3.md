# Major Issues — v3 Review (2026-07-30)

Basis: v2 sources (`Shikai-Jul28-IK_revised_v2.pdf`). Issues marked **[fixed in v3]**
were corrected in the v3 sources; issues marked **[open]** need an author decision
or new artifacts and were deliberately not changed.

## Logic and unsupported claims

1. **Overstated novelty claim in Discussion (RQ1)** [fixed in v3]
   The claim "no reviewed approach places collection and checking in separate
   processes while keeping the observation and checking components configurable"
   was contradicted by the thesis's own Related Work chapter: ROSMonitoring runs
   its oracle in a separate process behind WebSocket with a replaceable
   specification, Aldegheri et al. move containerized verifiers between edge and
   cloud, and the digital-twin approach discusses monitor placement options. The
   claim was narrowed to what the review actually supports: in the reviewed work,
   split solutions either fix the property logic inside generated components or
   tie the split to one oracle protocol, so the integrated/split choice is not
   itself a configuration option.

2. **Self-contradictory sentence in Discussion** [fixed in v3]
   "A complete action trace remains incomplete because..." — "complete ... remains
   incomplete" reads as a contradiction. Rephrased as "Action observation remains
   partial: ...".

3. **Weak causal opener in Related Work** [fixed in v3]
   "Monitoring papers use the same terms for different goals, so each selected
   approach is described using the following questions" — the premise did not
   support the conclusion. Rewritten to state the actual rationale (uniform
   criteria keep heterogeneous approaches comparable).

## Structure and figure–text consistency

4. **Caption did not describe its own figure (Design, overview figure)** [fixed in v3]
   The caption of the pipeline-components figure described "collectors,
   transformers, dispatchers, converters, verdict exporters", but the diagram
   (`Components.png`) actually shows *Monitors, Filters, Exporters* inside a
   *Robot Edge Node*, plus a *Feedback Runtime* and parameter/lifecycle/QoS
   observation that the prototype does not implement. The caption now describes
   what is shown, and both caption and body state explicitly that the overview
   contains architecture-only elements. This removes a contradiction between the
   figure and the stated prototype scope (Section 4.1.2 says parameters,
   lifecycle, and QoS events are unselected).

5. **Diagram vocabulary still differs from the text** [partially resolved 2026-07-30]
   `Components.png` uses labels (Data Processor, Monitors, Filters, DC_for_DSLn,
   LTL/STL/CTL Engine, Build & Containerize) that do not match the role names used
   everywhere else (collectors, transformers, dispatchers, converters, verdict
   services). The added bridging sentence mitigates this, but redrawing the figure
   with the thesis role names would remove the need for mental translation. The
   "Build & Containerize / Dockerfile" block is also barely discussed in the text.
   *Update:* `CodeGen.png` was redrawn as a TikZ figure
   (`figures/config_generation_model.tex`) with the root class renamed
   *DeploymentSpecification* (professor comment 79); `Components.png` remains as
   is. The four architecture-mapping diagrams were added to Section 6.11 as
   figures with source-attributing captions, paired with the existing mapping
   tables.

6. **Resource-use section duplicated its own table** [fixed in v3]
   The prose repeated every CPU/memory/latency number already in the table. The
   paragraph now interprets the two observations that matter (cost of the MQTT
   boundary; Raspberry Pi headroom) and leaves the numbers to the table.

## Consistency

7. **Mixed British/American spelling system** [fixed in v3]
   "organisation / centralised / decentralised / synchronised" (-ise) coexisted
   with "organization / serialization / realizes" (-ize). Standardized to Oxford
   spelling (-ize with "behaviour"), which the majority of the text already used.
   Internal LaTeX labels and the image filename `Deployment_Centralised.png` keep
   the old spelling (invisible to the reader; renaming them risks breakage).

8. **Terminology drift** [fixed in v3]
   - "deployment configuration" appeared once for what is elsewhere always the
     "deployment specification".
   - The converter was said to "change" records where the established verb is
     "convert" (the professor had explicitly requested "converts" earlier).
   - "ROS 2-facing" was used in Chapter 1 before its definition in Chapter 4; the
     Chapter 1 uses were removed or glossed inline at first occurrence.

9. **Hardcoded cross-reference** [fixed in v3]
   Background referred to "Section 2.1" as literal text instead of `\ref`; this
   would silently break under renumbering. A label was added and the reference
   now resolves automatically.

10. **Hyphenation typo rendering with a stray space** [fixed in v3]
    "system-under- monitoring" (line break after the hyphen) in the ROMoSu
    section rendered as "system-under- monitoring" in the PDF.

## Items to verify before submission [open]

11. **E4 vs E5 speed-verdict counts.** The "same mission" produces 20 robot-2
    speed transitions in E4 but 18 in E5. Separate runs can legitimately differ,
    but the text never says so; one sentence (e.g. run-to-run timing variation in
    Nav2/Gazebo) would preempt an examiner's question.

12. **Title-page date** is "Eindhoven, June 2026"; today is late July 2026 —
    confirm the intended defence/graduation month.

13. **Committee fields**: `\secondCommitteeMember{}` and `\thirdCommitteeMember{}`
    are empty in `main.tex`.

14. **Feature-model figure legibility**: the domain feature model is a sideways
    figure resized to 16.8 cm height. The professor previously flagged
    readability; check the smallest label at 100% zoom in the final PDF.
