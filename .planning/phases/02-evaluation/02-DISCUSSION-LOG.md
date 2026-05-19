# Phase 2: Evaluation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-19
**Phase:** 02-evaluation
**Areas discussed:** Musicality criteria, Audio generation scope

---

## Musicality criteria

### Q1 — Primary signal

| Option | Description | Selected |
|--------|-------------|----------|
| Listen-test only | Subjective listening is ground truth; metrics supporting only | ✓ |
| Quantitative + listen-test | Both gate the verdict | |
| Quantitative only | Just `event_stats()`, no subjective listening | |
| Comparative listen-test | A/B against MAESTRO ground truth per sample | |

**User's choice:** Listen-test only
**Notes:** Matches how the model will actually be used. Quantitative metrics from `event_stats()` are reportable context but not gating.

### Q2 — Verdict format

| Option | Description | Selected |
|--------|-------------|----------|
| Binary per sample | Musical or not | |
| Scored rubric (1–5) | Multi-dimension scoring | ✓ |
| Free-form notes only | No numeric score | |
| Pass/fail + note | Binary + one-sentence reason | |

**User's choice:** Scored rubric (1–5)

### Q3 — Rubric dimensions (multi-select)

| Option | Description | Selected |
|--------|-------------|----------|
| Pitch coherence | Notes stay in a key/mode | |
| Rhythmic feel | Pulse, density, breathing | ✓ |
| Phrase shape | Build / peak / resolve arcs | ✓ |
| Dynamics & expression | Velocity variation, pedal, accents | ✓ |

**User's choice:** Rhythmic feel + Phrase shape + Dynamics & expression
**Notes:** Pitch coherence dropped — structural musicality matters more than note-choice correctness for a co-performer.

### Q4 — Deliverable

| Option | Description | Selected |
|--------|-------------|----------|
| EVAL.md in phase dir | Markdown table at `.planning/phases/02-evaluation/02-EVAL.md` | ✓ |
| Spreadsheet (CSV) | At `data/generated/scores.csv` | |
| Inline in SUMMARY.md | Rolled into Phase 2 SUMMARY | |

**User's choice:** EVAL.md in phase dir

### Q5 — Reference anchoring

| Option | Description | Selected |
|--------|-------------|----------|
| Score in isolation | No reference clips | |
| Reference-anchored | Pre-session MAESTRO calibration | ✓ |
| Side-by-side per sample | Paired listening per WAV | |

**User's choice:** Reference-anchored

### Q6 — v2 baseline scoring

| Option | Description | Selected |
|--------|-------------|----------|
| v2 gets listened too | Generate v2 WAVs and score on rubric | ✓ |
| v2 stays numeric only | Just use v2 val_loss as reference | |

**User's choice:** v2 gets listened too
**Notes:** Required to answer the central question — is mel-conditioned training producing musical output, or just lower val loss?

### Q7 — Scale anchors

| Option | Description | Selected |
|--------|-------------|----------|
| 5 = MAESTRO, 1 = random | Simple extremes-based | |
| Define anchors per dimension | Spell out 1/3/5 for each dimension | ✓ |
| No formal anchors | Score on intuition | |

**User's choice:** Define anchors per dimension
**Notes:** Per-dimension anchor sheet to be authored as first task of Phase 2 execution (per CONTEXT.md deferred section).

### Q8 — Scorer

| Option | Description | Selected |
|--------|-------------|----------|
| You alone | Single listener | ✓ |
| Blind pass + replay | Listen unlabelled, then reveal | |
| Multi-rater | 2–3 listeners | |

**User's choice:** You alone

### Q9 — Listening environment

| Option | Description | Selected |
|--------|-------------|----------|
| Headphones (closed-back) | Consistent across sessions | ✓ |
| Studio monitors | Best fidelity in treated room | |
| Whatever's nearest | Laptop speakers / wireless earbuds | |

**User's choice:** Headphones (closed-back)

### Q10 — Session policy

| Option | Description | Selected |
|--------|-------------|----------|
| One sitting | Score all 27 WAVs in one ~30–60 min session | ✓ |
| Multiple sessions, same day | 2–3 sessions with breaks | |
| Multiple days | Sleep between sessions | |

**User's choice:** One sitting
**Notes:** Total listening was reduced further when sample length dropped to 5–10s — closer to 5–10 min total.

### Q11 — Soundfont

| Option | Description | Selected |
|--------|-------------|----------|
| Use bundled, accept caveat | `VintageDreamsWaves-v2.sf2` already resolved by synthesize.py | ✓ |
| Download a better piano SF2 | GeneralUser GS or Salamander | |
| Defer audio rendering | Score MIDI directly in a DAW/MuseScore | |

**User's choice:** Use bundled, accept caveat

### Q12 — Edge case handling

| Option | Description | Selected |
|--------|-------------|----------|
| Score it 1 across the board | Broken outputs become 1s with a note | ✓ |
| Score 'N/A', exclude | Drop from aggregate | |
| Re-generate with different seed | Replace broken samples | |

**User's choice:** Score it 1 across the board

---

## Audio generation scope

### Q13 — Prompt source

| Option | Description | Selected |
|--------|-------------|----------|
| BOS only | Unconditional, model improvises from BOS token | ✓ |
| MIDI prompts | Prime with 16 events from MAESTRO | |
| Both, separately scored | Both BOS and prompted | |

**User's choice:** BOS only
**Notes:** MIDI-prompted continuation deferred to Phase 3 (closer to co-performance use case).

### Q14 — Samples per (checkpoint, temp) cell

| Option | Description | Selected |
|--------|-------------|----------|
| 1 per temp (9 total) | Single sample per cell | |
| 3 per temp (27 total) | Averages sampling noise | ✓ |
| 5 per temp (45 total) | Higher confidence | |

**User's choice:** 3 per temp (27 total)

### Q15 — n_events per sample

| Option | Description | Selected (initial) | Revised |
|--------|-------------|--------------------|---------|
| 64 events (~15–20s) | Original recommendation | ✓ | |
| 128 events (~30–40s) | Reveals long-range phrase structure | | |
| 256 events (~60–80s) | Diminishing returns | | |

**User's choice (revised):** 32 events (~5–10s) — typed as freeform after the initial 64-event answer.
**Notes:** Speed-first call. Phrase-shape dimension becomes less reliable at this length (single phrase or mid-phrase cutoff) — captured in CONTEXT.md D-02 / D-08.

### Q16 — Temperature scope

| Option | Description | Selected |
|--------|-------------|----------|
| 0.7 / 0.9 / 1.1 only | Per EVAL-03/04 acceptance criteria | ✓ |
| Add 0.5 and 1.3 | Probe extremes | |
| Just 0.9 (one temp) | Skip sweep | |

**User's choice:** 0.7 / 0.9 / 1.1 only

---

## Claude's Discretion

The following were not explicitly asked but flagged as Claude-decides in CONTEXT.md:
- WAV output directory layout (`data/generated/{v2,v3,v4}/`)
- WAV file naming convention
- Random seed policy (random per generation unless reproducibility is needed)
- `top_k` sampling parameter (existing default = 50)
- Whether to use `--compile` / `--bf16` flags during gen
- WAV commit policy (planning to gitignore `data/generated/`)

## Deferred Ideas

- v4 fate decision (re-train vs accept) — defer until EVAL.md scores in
- Long-term WAV retention policy — revisit at milestone-complete
- Mel patch generation at inference — incompatible with <10ms target
- MIDI-prompted generation — Phase 3
- Multi-rater listening — only if public release is on the roadmap
- Per-dimension anchor sheet — author as Phase 2 execution Task 1
