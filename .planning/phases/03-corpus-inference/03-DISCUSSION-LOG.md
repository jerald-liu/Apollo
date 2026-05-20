# Phase 3: Corpus & Inference — Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-20
**Phase:** 03-corpus-inference
**Areas discussed:** Corpus conventions, Real training setup, Sampling defaults + stop condition

---

## Corpus conventions

| Option | Description | Selected |
|--------|-------------|----------|
| 120 BPM | Standard, easy in Ableton, matches smoke-train | ✓ |
| One BPM, not 120 | User-chosen target, all pairs within ±2 | |
| Multiple BPMs | More variety, requires per-pair BPM tracking | |

**User's choice:** 120 BPM

---

| Option | Description | Selected |
|--------|-------------|----------|
| Varied presets | Mix bright plucks, pads, percussive FM | ✓ |
| One preset, then expand | Single preset for all v1 pairs | |
| You decide | Claude picks | |

**User's choice:** Varied presets (recommended)

---

| Option | Description | Selected |
|--------|-------------|----------|
| Free — any key/scale | Natural authoring, absolute pitch bins | ✓ |
| Single key for v1 | Reduce variation dimensions | |

**User's choice:** Free — any key/scale

---

| Option | Description | Selected |
|--------|-------------|----------|
| Defer augmentation again | Too much overhead before loop is proven | ✓ |
| Build pitch-shift in Phase 3 | 11× data, but requires manual mel re-render | |
| Pitch-shift MIDI only | Misaligns mel conditioning | |

**User's choice:** Defer again

---

| Option | Description | Selected |
|--------|-------------|----------|
| 0.5–1.5s, 2–6 notes | Matches PROJECT.md tiny-gesture spec | ✓ |
| Push ceiling — up to 2s / 8 notes | More musical, uses seq_len slack | |
| You decide pair-by-pair | Organic but harder to reason about | |

**User's choice:** 0.5–1.5s, 2–6 notes (recommended)

---

| Option | Description | Selected |
|--------|-------------|----------|
| Varied response types | Natural authoring, Jerald-shape as target | ✓ |
| One relationship type for v1 | Cleaner signal, constrains musical voice | |

**User's choice:** Varied (recommended)

---

| Option | Description | Selected |
|--------|-------------|----------|
| Same preset both sides | Call and response same timbre | |
| Different presets per pair | Adds timbre-shift dimension | |
| Both valid / user choice | ✓ |

**User's choice (freeform):** "both should be possible and might be a user choice while using Apollo"
**Notes:** Pairs can have same or different presets. At inference time the user picks the response preset in Ableton anyway (model outputs MIDI only). No constraint enforced in corpus authoring.

---

## Real training setup

| Option | Description | Selected |
|--------|-------------|----------|
| New train.py | Clean separation from smoke-train CI artifact | ✓ |
| Extend train_smoke.py | Simpler but conflates wiring check with real training | |

**User's choice:** New train.py (recommended)

---

| Option | Description | Selected |
|--------|-------------|----------|
| Warmup + cosine decay | Standard for transformers, D-16 carry-forward | ✓ |
| Flat LR, no schedule | Simpler; AdamW already worked in smoke train | |

**User's choice:** Warmup + cosine decay (recommended)

---

| Option | Description | Selected |
|--------|-------------|----------|
| models/run-{iteration}-{timestamp}.pt | Iteration-indexed for Phase 4 comparison | |
| models/checkpoint-{epoch}-{timestamp}.pt | Epoch-indexed, loses iteration context | |
| You decide | ✓ |

**User's choice:** Claude's discretion — chose `run-{iteration:02d}-{timestamp}.pt`

---

| Option | Description | Selected |
|--------|-------------|----------|
| 200–500 epochs | Fast to iterate, configurable via flag | ✓ |
| Just a flag, no default | Always require --epochs | |
| You decide | | |

**User's choice:** 200–500 epochs — default 300, overridable via `--epochs`

---

| Option | Description | Selected |
|--------|-------------|----------|
| Log held-out loss every N epochs | Cheap, early overfitting signal | ✓ |
| Training loss only | Simpler, Phase 4 handles evaluation | |

**User's choice:** Yes — log held-out loss every N epochs (default every 10)

---

## Sampling defaults + stop condition

| Option | Description | Selected |
|--------|-------------|----------|
| Temperature 0.8 | Slightly conservative, good for small corpus | ✓ |
| Temperature 1.0 | Raw logits, more variety | |
| Temperature 0.5 | Sharp distribution, may cause repetition | |

**User's choice:** 0.8 (recommended)

---

| Option | Description | Selected |
|--------|-------------|----------|
| top-k=10 | ~9% of active vocab, plausible tokens | ✓ |
| top-k=50 | Nearly half vocab, more variety | |
| No top-k | Pure temperature sampling | |

**User's choice:** top-k=10 (recommended)

---

| Option | Description | Selected |
|--------|-------------|----------|
| EOS OR max_tokens | Primary stop + fallback, prevents runaway | ✓ |
| Max time budget | More musical but more complex | |
| EOS only | Risk of infinite loop if model doesn't converge | |

**User's choice:** EOS OR max_tokens (default max_tokens=24)

---

| Option | Description | Selected |
|--------|-------------|----------|
| Skip and continue | Partial output > crash during early iteration | ✓ |
| Stop, return partial | Safer, ensures valid MIDI | |
| Raise an error | Too strict for early training | |

**User's choice:** Skip and continue (recommended)

---

| Option | Description | Selected |
|--------|-------------|----------|
| Read from call MIDI file | Correct by design, already available | ✓ |
| Hardcode 120 BPM | Simpler but brittle | |

**User's choice:** Read from call MIDI file (recommended)

---

| Option | Description | Selected |
|--------|-------------|----------|
| response_001.mid alongside call.mid | Easy to audition in Ableton, zero-padded | ✓ |
| generate/{call_name}/response_{N}.mid | Organized but separate from source | |
| User-specified output dir | Flexible but requires flag always | |

**User's choice:** response_001.mid alongside call.mid (recommended)

---

## Claude's Discretion

- Checkpoint naming: `models/run-{iteration:02d}-{timestamp}.pt`
- `train.py` and `generate.py` CLI flag names beyond the discussed ones
- Log CSV format for per-run training history
- Whether `generate.py` emits a human-readable summary alongside the MIDI

## Deferred Ideas

- Pitch-shift augmentation — deferred again (D-07); revisit in v2
- generate.py CLI design details (flags, progress) — Claude's discretion
- FM patch generation head — SEED-001, backlog 999.1
