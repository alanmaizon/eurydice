# CLAUDE.md

## Mission

You are working on **Eurydice**, an AI music-teaching product focused first on guitar.

Your job is to help transform the existing codebase into a **domain-agnostic teaching engine** with **Eurydice as the active domain module**.

The product goal is not “audio analysis” and not “chat.”  
The product goal is:

> **measurable, repeatable musical progress**

The core user outcome is:

> **A guitarist reliably masters a short passage they care about (10–30 seconds) to a defined standard of timing and note accuracy, and can repeat it on demand.**

Every architectural and product decision should support that outcome.

---

## North Star

### Product North Star
**Weekly Mastery Events per Active User (WME/AU)**

A **Mastery Event** occurs when a user achieves repeated successful passes of the same passage under a defined mastery gate.

### Mastery Gate
A passage is only considered mastered when:
- the user completes **N consecutive passes** of the same passage
- each pass meets the minimum timing threshold
- each pass meets the minimum note correctness threshold
- the tool confidence is above the minimum confidence gate
- no low-confidence analysis is being silently treated as reliable

Default initial target:
- `consecutive_passes_required = 3`
- `timing_score >= 0.85`
- `note_score >= 0.80`
- `confidence >= 0.70`

These values are starting points, not fixed truths. Keep them configurable.

---

## Non-Negotiable Product Rules

1. **Mastery-loop first**
   Every session must drive toward:
   - diagnose
   - drill
   - retry
   - verify mastery

2. **Do not bluff**
   If the system is not confident, it must say so and ask for a better take, slower tempo, cleaner audio, isolated guitar, or a better camera angle.

3. **One high-leverage correction at a time**
   Feedback should prioritize the single most important fix before listing secondary issues.

4. **Evidence before explanation**
   Feedback must be grounded in measured artifacts:
   - timing drift
   - missed notes
   - wrong pitches
   - alignment errors
   - posture / technique flags
   Never invent musical certainty.

5. **Fast path + deep path**
   Eurydice should feel responsive.
   - quick feedback first
   - heavy analysis second

6. **Pedagogy over verbosity**
   Do not produce long impressive explanations.
   Prefer:
   - one correction
   - one drill
   - one success criterion

---

## Claude Role Boundaries

Claude is the **teaching and orchestration layer**, not the raw audio engine.

Claude should do:
- tool selection
- tool sequencing
- session-state-aware coaching
- prioritization of the highest-impact correction
- drill generation
- mastery decision support
- user-facing explanation and motivation

Claude should not do:
- raw DSP
- note transcription internally
- beat detection internally
- pitch extraction internally
- fake listening claims
- unsupported claims about accuracy when tool confidence is low

Never say or imply:
- “I listened directly to your audio”
- “I know exactly what you played”
unless that conclusion is explicitly backed by tool outputs.

---

## Critical Technical Constraint

Assume Claude is used as:
- reasoning layer
- pedagogy layer
- multimodal interpretation layer for tool outputs and images

Do **not** assume native realtime audio understanding comparable to a dedicated audio-native API stack.

Architecture must therefore treat:
- **audio tools as the ears**
- **vision tools as the eyes**
- **Claude as the teacher**

---

## Domain Sanitization Rule

There may be prior domain-specific code in the repository from an earlier product.

### Required behavior
Do **not** preserve prior domain names, modules, prompts, events, or schemas as active architectural concepts.

Instead:
- extract reusable primitives into a **generic teaching engine**
- rename domain-specific identifiers into neutral engine concepts
- remove legacy domain names from active code paths
- avoid carrying forward branded or topic-specific namespaces
- keep only what is technically reusable

### Important
The previous domain should be treated only as a **legacy source of reusable implementation ideas**, not as a retained module identity.

Bad:
- preserving old domain namespace as a first-class module
- new code depending on legacy prompts or domain types
- mixed terminology across engine and Eurydice

Good:
- generic engine abstractions
- clean Eurydice module on top
- legacy-specific assumptions removed or isolated

---

## Required Target Architecture

### 1. Generic teaching engine
Create or refactor toward a domain-agnostic engine responsible for:
- session lifecycle
- orchestration loop
- tool contracts
- confidence propagation
- telemetry
- evaluation hooks
- retry / recovery behavior
- state transitions

Suggested structure:

- `engine/`
  - `runtime/`
  - `orchestration/`
  - `sessions/`
  - `contracts/`
  - `telemetry/`
  - `evaluation/`
  - `utils/`

### 2. Eurydice domain module
Eurydice should live as a clean domain implementation on top of the engine.

Suggested structure:

- `domains/eurydice/`
  - `pedagogy/`
  - `scoring/`
  - `content/`
  - `pipelines/audio/`
  - `pipelines/vision/`
  - `prompts/`
  - `schemas/`
  - `ui/`

### 3. Applications
- `apps/web/`
- `apps/api/`

### 4. Evaluation
- `eval/offline/`
- `eval/online/`
- `eval/human/`

---

## Required Session Model

Design the Eurydice loop as an explicit state machine.

Minimum states:
- `idle`
- `target_selected`
- `recording`
- `processing_quick`
- `feedback_quick`
- `processing_deep`
- `feedback_deep`
- `drill_assigned`
- `retry_requested`
- `mastered`
- `capture_invalid`
- `error`

Each transition should be explicit and testable.

---

## Backbone Workflow

The core loop should behave like this:

1. user selects or defines a target passage
2. user records attempt
3. quick audio analysis runs
4. if confidence is too low:
   - request improved capture
   - do not continue as if reliable
5. if confidence is acceptable:
   - produce quick feedback
6. if needed:
   - run deep analysis
   - optionally run vision analysis
7. Claude interprets outputs
8. Claude returns:
   - one primary correction
   - one drill
   - one success criterion
9. user retries
10. mastery gate is checked
11. if passed:
   - log mastery event
   - suggest next progression step

---

## Two-Speed Analysis Design

### Quick analysis
Optimize for speed and responsiveness.

Use for:
- onset / tempo estimation
- rough pitch confidence
- obvious timing drift
- simple pass/fail guidance
- capture quality checks

Target:
- first useful feedback should arrive quickly

### Deep analysis
Use when:
- user wants detailed diagnosis
- quick analysis indicates likely but uncertain issues
- backing track or noise is present
- note-level alignment is needed

Use for:
- transcription
- source separation
- alignment to reference
- error localization
- richer scoring
- vision-assisted technique flags

---

## Tooling Strategy

### audio_analysis
This is a deterministic tool service, not a vague model capability.

It should expose at minimum:
- `mode`: `quick | deep`
- `tempo_bpm`
- `tempo_confidence`
- `beat_times_s`
- `note_events`
- `pitch_track_hz`
- `pitch_confidence`
- `alignment`
- `performance_scores`
- `warnings`
- `input_quality`
- `analysis_confidence`

### vision_analysis
This should remain optional for early milestones but must follow a clean schema.

It should expose at minimum:
- `hands_detected`
- `hand_landmarks`
- `handedness`
- `technique_flags`
- `capture_warnings`
- `analysis_confidence`

### orchestration
Claude is the orchestration layer.
Wrap Claude in a deterministic controller that:
1. requests a structured plan
2. executes tools
3. requests a learner-facing response
4. validates response shape before showing it

Do not let orchestration drift into freeform unstructured behavior.

---

## Initial Audio Stack Guidance

Use the stack pragmatically, not dogmatically.

### Strong candidates
- **Basic Pitch**
  - phrase-level note transcription
  - useful for audio-to-MIDI conversion
- **librosa**
  - analysis glue
  - DTW alignment
  - feature extraction
- **CREPE**
  - monophonic pitch tracking
- **Demucs**
  - optional source separation when backing tracks interfere
- **Essentia**
  - powerful MIR feature extraction, but treat licensing carefully
- **aubio**
  - useful for low-latency analysis, but treat licensing carefully

### Licensing caution
Before hardwiring any AGPL/GPL component into the core production path:
- flag it clearly
- isolate it architecturally
- prefer permissive-license options when possible
- never silently bake a licensing risk into the backbone

---

## Research-Informed Reasoning Policy

Use reasoning selectively.

Audio-CoT-style findings suggest:
- reasoning can help on easier and medium-difficulty tasks
- reasoning may degrade performance on hard tasks if the chain becomes confusing
- longer reasoning can correlate with better results, but not always

Therefore:

### Do
- use deeper reasoning when tool evidence is strong
- use deeper reasoning when the user is stuck and more interpretation is needed
- scale reasoning only when confidence and latency budgets allow

### Do not
- generate long rationales by default
- treat extra verbosity as intelligence
- hide uncertainty behind polished explanations

### Product implication
Prefer:
- short evidence-backed coaching by default
- deeper diagnosis only when warranted
- visible evidence, not hidden internal chain-of-thought

---

## Required Feedback Format

Unless a UI contract says otherwise, user-facing feedback should be compact and structured.

Default response shape:
- `primary_correction`
- `why_it_matters`
- `drill`
- `success_criterion`
- `confidence_note` (only when needed)

Example style:
- specific
- musical
- timestamped if possible
- string/fret aware if available
- not patronizing
- not robotic

---

## Eurydice Pedagogy Rules

The teacher persona should be:
- precise
- encouraging
- evidence-based
- concise
- non-bluffing

Pedagogical priorities:
1. timing first when timing is the dominant issue
2. note accuracy when wrong notes dominate
3. technique only when visual evidence is strong enough
4. avoid overloading beginners with multiple simultaneous corrections
5. prefer drills that can be completed in 20–60 seconds

Every drill should target a specific failure mode.

---

## Metrics That Must Exist

At minimum, implement and track:

### Product metric
- `weekly_mastery_events_per_active_user`

### Session metrics
- `attempt_count_per_passage`
- `time_to_first_feedback`
- `time_to_mastery`
- `retry_rate`
- `capture_failure_rate`

### Model/tool quality metrics
- `timing_score`
- `note_score`
- `overall_score`
- `analysis_confidence`
- `false_mastery_rate`
- `low_confidence_block_rate`

### Trust metrics
- `user_disagreement_reports`
- `feedback_retraction_rate`
- `low_confidence_override_count`

---

## MVP Scope

### MVP definition
Build the **passage mastery loop** for **short, mostly monophonic guitar phrases** before attempting full song-level chord-heavy mastery.

### MVP must support
- choose or define short target phrase
- record attempt
- run quick analysis
- optionally run deep analysis
- return one correction + one drill + one success criterion
- retry loop
- mastery gate
- progress logging

### MVP should not try to solve yet
- full polyphonic music understanding
- full song orchestration
- advanced arrangement analysis
- broad genre-level theory coaching
- complicated multi-camera technique inference

---

## Required Migration Behavior

When auditing the current repository:

### First
Identify:
- reusable runtime pieces
- reusable streaming/session pieces
- reusable UI pieces
- reusable tool infrastructure
- reusable event pipelines

### Then
Classify everything into:
- keep and generalize
- keep and move under Eurydice
- delete
- rewrite

### Important rule
Do not perform a shallow rename.
Perform a **conceptual extraction**:
- generic behavior goes into engine
- music-specific behavior goes into Eurydice
- legacy-domain assumptions are removed

---

## Concrete Deliverables Expected From Claude

When working in this repo, produce:

1. **Architecture audit**
   - what exists
   - what is reusable
   - what is domain-specific
   - what blocks Eurydice

2. **Refactor plan**
   - smallest viable path first
   - minimal invasive changes before major rewrites

3. **Folder structure proposal**

4. **Typed contracts**
   - session contracts
   - audio analysis contracts
   - vision analysis contracts
   - coaching response contracts

5. **Implementation roadmap**
   - milestone order
   - dependencies
   - risk notes

6. **Code changes**
   - concrete patches, not just advice

7. **Evaluation plan**
   - offline
   - online
   - human review

---

## Coding Behavior Expectations

When editing code:

- prefer incremental refactors over large speculative rewrites
- keep code production-oriented
- preserve working behavior where possible
- document assumptions
- isolate placeholders clearly
- add explicit types
- add schema validation
- propagate confidence scores end-to-end
- avoid hidden magic behavior
- make state transitions observable
- keep telemetry hooks in place

When uncertain:
- state the uncertainty
- choose the smallest reversible path
- avoid inventing unsupported capabilities

---

## What Claude Should Do First

On entering the repo, do this in order:

1. audit the current architecture
2. identify all domain-specific naming and assumptions
3. extract generic engine primitives
4. define Eurydice domain boundaries
5. define session state machine
6. define audio and vision tool schemas
7. wire the minimum mastery loop
8. only then improve UX and polish

---

## Immediate Objective

Your immediate objective is:

> **Create the smallest viable Eurydice prototype that can take a short guitar phrase, analyze it through deterministic tools, interpret the results through Claude, return one actionable correction and one drill, and verify mastery through repeated passes.**

Do not optimize for demo flash before this loop works.

---

## Default Output Mode For Repo Work

When responding during implementation work, prefer this structure:

1. **Observed**
2. **Decision**
3. **Patch plan**
4. **Code changes**
5. **Risks**
6. **Next validation step**

Be concrete. Avoid generic advice.
