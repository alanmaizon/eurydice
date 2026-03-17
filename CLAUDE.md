# CLAUDE.md

## Project: Eurydice

Eurydice is a multimodal AI music-teaching product focused first on guitar.

This repository may contain ideas, patterns, or infrastructure that originated in a different teaching domain. Do **not** preserve that prior domain as a visible namespace, product concept, prompt identity, or architectural dependency.

### Domain sanitization rule

A previous domain may exist in the codebase as legacy implementation detail only. Your job is to **sanitize** it out of the active architecture.

That means:

- do **not** keep prior domain names in public modules, prompts, events, schemas, UI copy, or package boundaries
- do **not** preserve legacy domain branding as the default abstraction
- do **not** build Eurydice as a thin rename over a prior domain-specific app
- do build a **domain-agnostic teaching engine**
- do implement **Eurydice** as a clean domain module on top of that engine
- if legacy code is reused, isolate it behind neutral interfaces and rename aggressively

Treat any prior domain as:
- a source of reusable runtime patterns
- a migration reference
- a legacy module that should not leak into the new product surface

---

## North Star

The product must optimize for one outcome:

**A guitarist reliably masters a short passage they care about (10–30 seconds) to a defined standard of timing and note accuracy, and can repeat it on demand.**

Do not optimize for:
- chat quality alone
- transcription novelty
- generic encouragement
- raw feature count
- vague “AI coach” behavior

Optimize for:
- measurable progress
- repeatable mastery
- tight correction loops
- trustworthy feedback
- fast iteration toward a successful next take

---

## Product definition

Eurydice should feel like:

- a live teacher
- a measurement-driven coach
- a short-loop practice system
- “Guitar Hero, but real”

The user experience should be:

1. choose or define a short passage
2. record a take
3. analyze timing, notes, and optionally technique
4. identify the single highest-leverage correction
5. prescribe one short drill
6. retry
7. declare mastery only when the gate is met

---

## Hard architectural constraints

### Claude role boundary

Claude is the **teaching and orchestration layer**.

Claude is responsible for:
- tool planning
- interpretation of analysis outputs
- pedagogical prioritization
- learner-facing responses
- session memory and progression logic
- deciding when more evidence is needed

Claude is **not** the raw audio analysis engine.

Do not assume native realtime audio understanding as the core backend primitive.

Instead:

- audio tools produce measurements
- vision tools produce technique observations
- Claude consumes structured outputs with confidence values
- Claude turns those outputs into coaching

### Confidence rule

Never smooth over uncertainty.

If analysis confidence is low:
- ask for a better take
- request slower tempo
- request cleaner capture
- request isolated instrument input
- request different camera angle

Do not hallucinate technique advice from weak evidence.

---

## Backbone principles

1. **Mastery-loop first**
   Every session should drive toward a mastery decision, not a conversation.

2. **Measurement before explanation**
   Feedback must be grounded in tool outputs.

3. **One correction first**
   Prefer the highest-leverage fix over broad feedback dumps.

4. **Two-speed analysis**
   Return quick feedback fast, then deeper analysis if needed.

5. **Confidence-aware coaching**
   Every important inference should respect tool confidence.

6. **Domain-agnostic core**
   Reusable runtime belongs in core. Eurydice-specific logic belongs in a domain module.

7. **No legacy domain leakage**
   Legacy names, types, prompts, routes, events, and copy must be sanitized.

---

## Primary user loop

The main loop is:

1. user selects a passage and target tempo
2. user records audio and optional camera input
3. system runs quick analysis
4. if confidence is too low, request better input
5. if confidence is sufficient, score and localize the top issue
6. if needed, run deep analysis
7. Claude generates:
   - one primary correction
   - one short drill
   - one success criterion for the next take
8. user retries
9. system checks mastery gate
10. if passed, log a mastery event and recommend next progression step

---

## Mastery model

A passage is considered mastered only when the user achieves repeated acceptable performance under explicit thresholds.

### Mastery gate

A **Mastery Event** occurs when the user completes:

- **3 consecutive passes**
- on the **same passage**
- meeting:
  - timing threshold
  - note accuracy threshold
  - minimum confidence threshold

Do not declare mastery from a single lucky pass.

### North Star metric

Track:

**Weekly Mastery Events per Active User (WME/AU)**

Use this as the product-level decision metric.

Features that do not improve mastery outcomes are lower priority.

---

## Initial product scope

Focus the MVP on:

- short guitar passages
- single-note or monophonic-ish phrases first
- timing + pitch/note scoring
- retry loop with measurable progress
- optional vision-assisted technique cues

Do **not** start with:
- full song intelligence
- rich social features
- advanced composition tools
- broad multi-instrument support
- full polyphonic correctness claims
- ornate dashboards before trust is established

---

## Required architecture shape

## 1. Core runtime

Create or refactor a reusable runtime layer for:

- session orchestration
- tool registry
- state transitions
- retry handling
- tracing
- structured outputs
- confidence propagation
- evaluation hooks

Suggested neutral pathing:

- `core/agent_runtime/`
- `core/schemas/`
- `core/session/`
- `core/eval/`

This layer must not contain music-specific or legacy-domain-specific assumptions.

## 2. Eurydice domain module

Implement Eurydice as a domain module with:

- pedagogy
- scoring
- audio pipelines
- vision pipelines
- exercise content
- mastery logic

Suggested structure:

- `domains/eurydice/pedagogy/`
- `domains/eurydice/scoring/`
- `domains/eurydice/pipelines/audio/`
- `domains/eurydice/pipelines/vision/`
- `domains/eurydice/content/`
- `domains/eurydice/prompts/`
- `domains/eurydice/types/`

## 3. Legacy isolation

If legacy code exists, isolate it under something like:

- `legacy/`
- or `domains/legacy_<name>/`

Do not keep it in the active runtime path unless explicitly needed during migration.

---

## Analysis pipeline

## Quick analysis path

This path should be optimized for speed and flow.

Use it for:
- onset timing
- tempo drift
- rough pitch correctness
- obvious wrong notes
- basic confidence estimation

Target:
- first meaningful feedback should arrive quickly enough to preserve practice flow

## Deep analysis path

This path is for:
- transcription refinement
- alignment against target
- source separation when backing track interferes
- better error localization
- richer scoring
- optional technique cross-checking

Trigger deep analysis only when it materially improves the next teaching action.

---

## Audio tool responsibilities

Build the audio layer as a structured pipeline, not a monolith.

Possible capabilities include:

- onset detection
- tempo estimation
- beat tracking
- pitch tracking
- note event extraction
- phrase alignment against target
- confidence scoring
- source separation when needed
- capture-quality warnings

### Audio output contract

Standardize the audio analyzer output around a neutral schema such as:

- `tempo_bpm`
- `tempo_confidence`
- `beat_times_s`
- `note_events`
- `pitch_track_hz`
- `pitch_confidence`
- `alignment`
- `performance_scores`
- `warnings`

Where possible, include:
- timing score
- note score
- overall score
- timestamped error regions
- capture warnings

---

## Vision tool responsibilities

Vision is supportive, not primary, in early versions.

Use it for:
- hand presence
- hand landmarks
- fretboard visibility
- posture hints
- picking/fretting technique flags
- camera quality warnings

### Vision output contract

Standardize output around a neutral schema such as:

- `hands_detected`
- `hand_landmarks`
- `handedness`
- `technique_flags`
- `capture_warnings`

Only surface technique advice above confidence threshold.

---

## Claude orchestration policy

Claude must act as a strict evidence-based teacher.

### Claude should do

- decide which tool to call next
- decide whether quick analysis is sufficient
- decide whether deep analysis is worth latency
- identify the single most important correction
- generate a short drill
- define one clear success criterion
- keep the user in a tight mastery loop
- maintain session continuity and progression state

### Claude should not do

- pretend it directly heard raw audio if it did not
- invent technique diagnoses without evidence
- overload the learner with too many fixes
- produce long persuasive reasoning that outruns the evidence
- declare mastery on weak or noisy signals

### Response format rule

For each attempt, prefer output shaped like:

- **Observed issue**
- **Likely cause**
- **Next drill**
- **Success criterion for next take**

Keep it concise, specific, and instructional.

---

## Reasoning policy

Use reasoning selectively.

Longer reasoning is not automatically better. For hard auditory tasks, excessive reasoning may degrade performance instead of helping. The Audio-CoT paper reports that CoT methods helped on easier and medium tasks but degraded on harder ones, while also showing a positive relationship between longer reasoning paths and accuracy in some settings. :contentReference[oaicite:0]{index=0}

Translate that into product policy:

- use shallow reasoning by default
- use deeper reasoning only when evidence is strong and the latency budget allows
- when the task is hard and confidence is weak, prefer data collection over more speculation
- expose evidence to the user, not internal hidden reasoning

Examples:
- “Your note entries are late around 4.2s–5.1s”
- “The bend is under pitch on the second repetition”
- “Camera angle hides the fretting hand; retake from neck side”

---

## Evaluation philosophy

Evaluation must cover more than raw audio scoring.

Adopt four internal evaluation lanes:

1. **Auditory processing**
   Can the system measure timing, pitch, and alignment correctly?

2. **Reasoning**
   Does it choose the right diagnosis and drill?

3. **Dialogue / teaching loop**
   Does it keep the learner progressing without confusion?

4. **Trust / safety**
   Does it avoid confident wrong feedback and unsafe advice?

Build evaluation around:
- offline benchmark performance
- human teacher comparison
- online mastery improvement
- wrong-feedback reports

---

## MVP milestones

## Milestone A: Core mastery loop

Deliver:
- passage selection or definition
- short recording flow
- quick timing + pitch scoring
- one correction + one drill
- mastery gate logic
- confidence-based fallback messaging

Acceptance:
- user can retry in a clean loop
- low-confidence cases do not bluff
- mastery event logging works

## Milestone B: Deep analysis

Deliver:
- note-event extraction
- better alignment
- deeper scoring
- optional source separation when needed

Acceptance:
- deep analysis materially improves diagnosis
- progress across retries is measurable

## Milestone C: Vision-assisted coaching

Deliver:
- hand landmarks
- 2–3 technique flags
- camera guidance for better capture

Acceptance:
- only confident flags are shown
- flags are understandable and actionable

## Milestone D: Song-mode expansion

Deliver:
- reference alignment for larger material
- automatic subdivision into micro-passages
- progression across a section, not just one lick

Acceptance:
- section-level mastery works without destroying trust

---

## Refactor mandate

When inspecting the current repo:

1. identify reusable runtime components
2. identify domain-specific prompts, events, types, tools, and copy
3. move reusable logic into neutral core modules
4. move prior-domain artifacts into legacy or archive paths
5. create clean Eurydice modules on top
6. rename aggressively to remove domain leakage
7. preserve behavior where useful, but not naming or conceptual coupling

### Explicit sanitization targets

Sanitize all of the following if they reference the old domain:

- folder names
- type names
- prompt files
- event names
- websocket message names
- UI labels
- CSS/test IDs if domain-specific
- telemetry event names
- system prompt language
- documentation
- example data
- tests
- screenshots or fixtures

Do not leave “temporary” legacy names in new production paths.

---

## Deliverables expected from Claude

When working in this repo, produce:

1. an architecture audit
2. a migration plan
3. a proposed folder structure
4. concrete refactors in priority order
5. tool contracts for audio and vision analysis
6. updated prompt architecture
7. session-state changes
8. mastery/scoring implementation
9. evaluation hooks
10. a usable first prototype path

Prioritize minimal invasive refactors first, but do not compromise the domain sanitization rule.

---

## First implementation target

The first usable prototype should support:

- record or upload a short guitar phrase
- run quick analysis
- optionally run deep analysis
- send structured analysis outputs to Claude
- return teacher-style feedback
- support a retry loop
- track measurable improvement
- declare mastery only when the gate is met

This is the first meaningful product checkpoint.

---

## Operating instructions for Claude

When you make changes:

- prefer small, verifiable steps
- keep production-oriented code quality
- preserve working infrastructure where appropriate
- add types and contracts before clever abstractions
- document assumptions
- highlight placeholder services clearly
- separate “measured”, “inferred