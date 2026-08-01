# Editing Notes — v3 (2026-07-30)

Scope of this pass: logic, flow, concision, terminology consistency, and removal
of formulaic phrasing. No content, data, citations, or claims were added. Minor
grammar fixes are not listed. The v3 PDF is `Shikai-Jul30-IK_revised_v3.pdf`,
built from the updated LaTeX sources with `build.ps1`.

## Abstract

- "verdicts matched controlled expectations, recorded inputs, mission outcomes,
  or Gazebo positions" → "matched the transitions of the controlled stimuli, the
  recorded inputs, the mission outcomes, or the simulated robot positions".
  "Controlled expectations" was ambiguous (expectations are not controlled; the
  stimuli are), and "Gazebo positions" assumed the reader already knows Gazebo.
- "serialization and MQTT preserved result meaning" → "did not alter the
  checking results". "Preserved result meaning" was vague; the evidence is
  concretely that the verdict streams were identical.

## Chapter 1 — Introduction

- The AI-uncertainty sentence now says these factors "affect a robot's behaviour
  after deployment" instead of "influence a robot", which was imprecise about
  what is influenced.
- "Testing … cannot cover every environment … Developers also need to observe"
  → "Developers therefore also need to observe": the causal link between the two
  sentences was implicit.
- Problem statement: the paragraph used "They have to decide …" four times in a
  row — a formulaic pattern. The five choices are kept intact (what, how, how
  much, property form, where) but the sentence structure now varies, and the
  what/how choices are merged into one sentence since they are the paired
  observation decisions.
- "The repeated implementation effort should be reduced by automation and by
  reusable, configurable infrastructure support" → active phrasing ("Reducing
  this repeated effort calls for …"); the passive "should be" left the agent and
  claim unclear.
- "ROS 2-facing" removed from the problem statement and Scope (the term is only
  defined in Chapter 4); at its first retained use in Approach, a short inline
  gloss "(a process that joins the ROS 2 graph)" was added.

## Chapter 2 — Background

- The chapter-opening roadmap paragraph ("It first introduces … It then explains
  … Finally, it introduces …") was compressed into one sentence listing the
  topics; the sentence-by-sentence signposting added length without information.
- Removed an orphan sentence in *Online and Offline Monitoring* ("The design
  question is where this monitoring logic should run…") that interrupted the
  online/offline contrast without contributing to it.
- "Approaches based on the other categories appear in Chapter 3, so the selected
  scope is not mistaken for the whole monitoring domain" — the justification
  read as defensive reviewer-speak; now simply forward-references Chapter 3.
- Replaced the literal "Section 2.1" with a proper `\ref` (new label
  `sec:ros2-communication`).
- MQTT QoS 2: "adds a stronger exactly-once exchange at the expense of a more
  involved protocol exchange" → "provides an exactly-once handshake at the cost
  of additional protocol traffic" (removed the double "exchange").
- Spelling normalized to Oxford style throughout the chapter (organizations,
  centralized, decentralized, synchronized); section/subsection titles updated
  accordingly. Internal labels and the `Deployment_Centralised.png` filename are
  unchanged.

## Chapter 3 — Related Work

- New opener explains why fixed criteria are used (comparability across
  approaches with overlapping terminology); the previous causal claim did not
  hold together.
- Fixed the "system-under- monitoring" line-break hyphenation in the ROMoSu
  section.
- Copilot disambiguation reworded ("Copilot here denotes a stream-based
  runtime-verification language and framework, not the identically named AI
  programming assistant") — same content, less abrupt.
- Section "Focused Summary" renamed "Comparison of the Reviewed Approaches" and
  its table caption aligned; "focused" was review-response vocabulary, not a
  description of the content.
- Final sentence "The proposed design is presented only after this neutral
  review" removed — it described the thesis's editing history rather than its
  content; the gap list now hands over to Chapter 4 directly.

## Chapter 4 — Design

- "A feature model is needed … to prevent one prototype configuration from being
  presented as the complete domain" → neutral phrasing about separating the
  domain description from the prototype configuration; the original stated a
  writing risk, not a design rationale.
- "recording constraints between branches as cross-tree notes" → "recording
  dependencies between branches as cross-tree constraints" ("cross-tree
  constraint" is the FODA term defined in Chapter 2; "notes" was undefined).
- **Overview figure caption rewritten** (substantive): it previously described a
  different decomposition (collectors/transformers/dispatchers) than the figure
  shows (monitors/filters/exporters in a robot edge node). Caption and body now
  describe the actual figure and state that it contains architecture-only
  elements (feedback runtime; parameter/lifecycle/QoS observation) that the
  prototype does not implement — this also removes a scope contradiction with
  Section 4.1.2.
- "A converter plug-in changes a common data record" → "converts" (consistent
  with the established converter terminology).
- "deployment configuration" → "deployment specification" (single deviating
  occurrence).
- R7 rephrased ("must be addable" → "It must be possible to add …").

## Chapter 5 — Implementation

- Dropped "This separation is important:" before the monitor/custom contrast —
  the sentence that follows demonstrates the importance; announcing it is
  filler.
- "Writing these files by hand is easy to get wrong" → "error-prone" (register).
- "Python additionally keeps project-specific converters and verdict services
  simple to add" → smoother phrasing.
- Chapter summary: "evaluates both this data path and the saved infrastructure
  work" → "evaluates this data path and the implementation work the
  infrastructure saves" ("saved infrastructure work" was ambiguous).

## Chapter 6 — Evaluation

- "Five experiments provide complementary rather than repetitive evidence" →
  "are designed to contribute complementary evidence" (the original pre-empted a
  criticism nobody had raised, which read as defensive).
- **Resource-use paragraph rewritten** (substantive): it restated every number
  from the table. It now interprets the two findings that carry the argument —
  the MQTT boundary raised mean record-to-verdict latency from 0.29 ms to
  1.85 ms, and the Raspberry Pi handled its full role within 13% of one core —
  and keeps the scalability qualifier.
- E4 conclusion: "source name keeps namespaces separate" → "the source-name
  field keeps the namespaced robot streams separate" (the field, not the name
  in general, is the mechanism).

## Chapter 7 — Discussion

- **RQ1 gap claim narrowed** (substantive): see Major Issues item 1. The revised
  wording claims only what Chapter 3 documents: split solutions in the reviewed
  work either fix property logic in generated components or bind the split to
  one oracle protocol, so placement is not itself a configuration choice there.
- "A complete action trace remains incomplete" → "Action observation remains
  partial: …".
- Converter/verdict-service description: "changes … into / changes its result
  into" → "transforms … into / returns its result in" (verb precision; avoids
  implying mutation).
- Spelling normalization (centralized ×2).

## Chapter 8 — Conclusions

- "implemented the selected path, and evaluated five increasingly distributed
  experiments" → "evaluated it in five increasingly distributed experiments"
  (one evaluates the artifact, not the experiments).
- RQ4 answer: "Within the tested scope, the support is demonstrated" → "the
  architecture and implementation supported the monitoring needs of the selected
  applications" (states what was demonstrated instead of pointing at it).

## Post-v3 update (same day)

- **"Oracle/checker" unified to "checker" thesis-wide** (author request). Two
  deliberate bridge mentions remain: the Background terminology definition notes
  "the literature also calls this component an oracle", and ROSMonitoring's
  first mention notes "(called an *oracle* in ROSMonitoring)" because that is
  the component's actual name in the cited paper. Both feature-model figures
  and all tables now say "Checker".
- **RQ1–RQ3 restatements in Discussion and Conclusions synchronized** with the
  reworded research questions in the Introduction, so the verbatim-repetition
  requirement (review item 104) still holds.

## Post-v3 update 2 (same day)

- **All em-dashes removed** (author request). Twelve prose uses of `---` were
  rewritten as parentheses, colons, or restructured sentences; the C1--C5 and
  R1--R7 label dashes became colons. En-dashes in ranges (E1--E4,
  request--response) are unchanged. Verified: zero em-dash glyphs in the PDF.
- **Accommodation status vocabulary simplified** (author request): table header
  "Status" is now "Support" with values "Yes" (configuration only),
  "Via plug-in", and "Extension point"; the jargon terms Direct/Adapter/
  Extension are gone. "Via plug-in" was kept as a third value rather than
  collapsing into "Yes" so the tables do not overstate out-of-the-box support.
- **Table 6.14** cleaned up: the long probes cell moved to a table footnote.
- **Figure 6.8 redesigned**: the previous four-boxes-and-arrows diagram (which
  carried almost no information and a typo) is now a grid summarizing, per
  approach, what is hosted by configuration, via plug-in, and at extension
  points, mirroring the tables.

## Post-v3 update 3 (same day)

- **Discussion 7.2/7.3 cleanups** (author request): dropped the
  "prototype boundary visible" sentence and the "Other variants would change
  the assumptions" passage; rewrote "Several unselected feature variants map
  onto the retained variation points..." as "Several features that the
  prototype does not implement would fit into the architecture without
  structural change"; fixed the elliptical "and a new checker a converter and
  verdict-service pair". Related jargon simplified elsewhere: "plug-in story"
  → "Plug-ins have a ... role", "simplifies the pipeline boundary" → plain
  wording, "unselected variation points" removed in Design 4.1.2 and
  Evaluation 6.10.
- **Transformer plug-ins**: investigation showed the `Transformer` base class
  existed but `build_transformer_pipeline` accepted only the three built-in
  names, unlike every other component kind. `monitor/runtime_builder.py` now
  resolves transformers through the shared plug-in resolver (import paths
  work; unknown types still warn and skip); all 15 related unit tests pass,
  and `docs/config_spec.md` was updated. The thesis mentions this once in
  Section 5.5.3 and once in the appendix plug-in contracts (new
  `transform()` contract), per the request to avoid repetition.

## Build note

- The spelling normalization initially renamed an image path
  (`Deployment_Centralised.png`) that must keep its on-disk name; the path was
  restored. The final build completes with zero unresolved references or
  citations.
