# Phase 2: Evaluation - Context

**Gathered:** 2026-05-19
**Status:** Ready for planning

<domain>
## Phase Boundary

Generate audio samples from v2, v3, and v4 checkpoints across the three locked
temperatures (0.7 / 0.9 / 1.1), conduct a single-listener rubric-scored listen
test, and write an EVAL.md that determines whether each checkpoint produces
musical output for the co-performance use case.

Out of scope for this phase:
- Re-training v4 with a different LR schedule (deferred — see Deferred Ideas)
- Real-time inference latency benchmarking (Phase 3)
- M4L integration (Phase 3 / next milestone)
- Mel patch generation at inference (deferred — no real-time path exists)

</domain>

<decisions>
## Implementation Decisions

### Musicality Criteria

- **D-01:** Primary signal is **listen-test only**. Quantitative metrics from
  `event_stats()` may be reported as context but do not gate the verdict.
- **D-02:** Score each sample on a **1–5 rubric across three dimensions**:
  - **Rhythmic feel** — steady pulse vs erratic, reasonable note densities,
    phrases that breathe vs everything-at-once dumps
  - **Phrase shape** — arcs (build / peak / resolve) vs flat streams (noted
    tradeoff with D-08: 5–10s samples will sometimes catch only a single
    phrase or a mid-phrase cut, lowering reliability of this dimension)
  - **Dynamics & expression** — velocity variation, pedal usage, intentional
    accents
  - Pitch coherence is explicitly **not** scored — for a co-performer,
    structural musicality matters more than note-choice correctness.
- **D-03:** Scale anchors must be **defined per dimension** before the
  listening session, not improvised mid-session. Write the anchor sheet first.
  Baseline anchors:
  - 5 = MAESTRO ground-truth level for that dimension
  - 1 = random keypresses / silence / generation failure
  - 3 = recognisable musical attempt with clear issues
  The 2/4 anchors are filled in per dimension when the anchor sheet is written.
- **D-04:** Each scoring session begins with **listening to 1–2 MAESTRO
  ground-truth clips** to recalibrate the ear (reference-anchored protocol).
- **D-05:** **v2 baseline is listened to and scored**, not just used as a
  numeric val-loss reference. The user's core concern is "is the architecture
  producing musical output at all" — v2 (val 2.1641) is the established
  baseline; if v2 sounds bad, v3's lower val loss doesn't help.
- **D-06:** **Single scorer** (project owner). No multi-rater protocol.
  Blind-pass listening is not required — the scorer knows which checkpoint
  each sample is from.

### Audio Generation Scope

- **D-07:** **BOS-only prompts** (unconditional generation). MIDI-prompted
  generation is deferred to Phase 3 (closer to the co-performance use case).
- **D-08:** **n_events = 32** per sample (≈5–10 seconds of audio). Chosen
  for fast iteration over deep phrase analysis. Tradeoff captured in D-02.
- **D-09:** **3 samples per (checkpoint, temperature) cell** to average out
  sampling noise. Total: 3 checkpoints × 3 temps × 3 samples = **27 WAVs**.
- **D-10:** **Temperatures: 0.7, 0.9, 1.1** — exactly the values locked in
  ROADMAP success criteria 3+4 and REQUIREMENTS EVAL-03/04. No expansion.

### Listening Protocol

- **D-11:** **Closed-back headphones** for consistent dynamic resolution
  across the session.
- **D-12:** **Single sitting** for all 27 WAVs (~5–10 min listening at
  ~10s per WAV plus scoring overhead). Re-anchor with MAESTRO clips at
  the start.
- **D-13:** **Bundled `VintageDreamsWaves-v2.sf2`** soundfont (already
  resolved by `synthesize.py`'s fallback chain). Soundfont fidelity caveat
  is noted in EVAL.md — the eval is about MIDI musicality, not audio
  fidelity. A mediocre soundfont reveals fewer expressive nuances but
  doesn't hide phrase / rhythm problems.
- **D-14:** **Edge case — broken outputs**: a WAV with too few notes,
  mostly silence, or any generation failure is scored **1 across all
  dimensions** with an explanatory note. Keeps the dataset closed and
  comparable; failure rate is visible in the table.

### Deliverable

- **D-15:** Output is **`.planning/phases/02-evaluation/02-EVAL.md`** —
  a markdown table with one row per (checkpoint, temperature, sample
  index) and columns for rhythmic, phrase, dynamics, and free-text notes.
  Followed by per-checkpoint summary paragraphs and a final go / no-go
  verdict per checkpoint for downstream use.

### Claude's Discretion

- WAV output directory naming (`data/generated/{v2,v3,v4}/` is the natural
  pattern given Phase 1's per-checkpoint Modal subdir convention)
- WAV file naming (e.g. `step{N}_t{temp}_s{sample_idx}.wav`)
- Random seed policy — random per generation by default; can be fixed
  for reproducibility if needed
- top_k sampling (existing generate.py default = 50 — keep unless reason
  to change)
- Whether to use `--compile` / `--bf16` flags during generation (these are
  the new fast-path flags; `--bf16` on Apple Silicon should be safe but
  worth a sanity check that bf16 output isn't audibly different)
- WAV commit policy: WAVs are binary artifacts and not git-friendly; the
  reasonable default is to gitignore `data/generated/` and reference
  them by path from EVAL.md. The EVAL.md scores are the durable record.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 2 Acceptance Criteria
- `.planning/REQUIREMENTS.md` — EVAL-01 through EVAL-06 are this phase's
  acceptance criteria.
  - EVAL-01, EVAL-02 already satisfied by Phase 1 (checkpoints pulled
    locally; see Phase 1 03-SUMMARY)
  - EVAL-05 already satisfied (v3 val_loss 2.1429 < 2.1641 baseline)
  - EVAL-03 and EVAL-04 are the audio-generation work this phase delivers
  - EVAL-06 is **not addressable by audio eval**: v4 best was at step 3,499
    (val 2.4298), the run never reached 80K steps with healthy descent.
    Documented as a research finding, deferred to a v4 re-training decision
    that lives outside this phase.
- `.planning/ROADMAP.md` § Phase 2 — success criteria 1–6

### Phase 1 Provenance
- `.planning/phases/01-training/01-03-SUMMARY.md` — checkpoint integrity
  verification, val loss values, run_name confirmation. Establishes that
  the checkpoint files this phase consumes are real (`map_location='cpu'`
  required for torch.load on Mac is also recorded there).
- `.planning/phases/01-training/01-CONTEXT.md` — Phase 1 decisions that
  carry forward (per-run checkpoint isolation, no augmentation for v4)

### Generation Code
- `scripts/generate.py` — entry point. After the Phase 2 fix it reads
  `vocab_size` and `n_mels` from checkpoint config, supports `--audio`
  (FluidSynth pipeline), `--compile`, and `--bf16`.
- `scripts/synthesize.py` — FluidSynth → WAV with a 3-tier fallback
  (FluidSynth+SF2 → EnCodec → additive sine). The bundled
  `VintageDreamsWaves-v2.sf2` is picked up automatically from the brew
  install of fluid-synth.
- `src/streaming_representation.py` — v4 (259-token) vocab decode path.
  Used implicitly through `tokens_to_events` resolution at checkpoint load.
- `src/model.py` — `ApolloModel` with KV-cache; the same model class
  loads v2, v3, and v4 with config-driven branching.

### Checkpoints
- `models/checkpoint_v2_best.pt` — v2 augmented baseline (val 2.1641,
  step 50K, base 380-token vocab, no mel)
- `models/checkpoint_v3_best.pt` — v3 mel conditioning (val 2.1429,
  step 33499, base 380-token vocab, MelEncoder present but **not used at
  inference** — no real-time mel patch path exists)
- `models/checkpoint_v4_best.pt` — v4 streaming (val 2.4298, step 3499,
  259-token vocab, target <2.3 missed)

### Specs
- `specs/representation.md` — base 380-token vocab definition
- `specs/preprocess.md` — preprocessing contract
- `specs/model.md` — model architecture contract

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- **`scripts/generate.py`** — already supports the exact use case: multi-
  temperature audio generation in one invocation. Example:
  ```
  venv/bin/python3 scripts/generate.py \
    --checkpoint models/checkpoint_v3_best.pt \
    --audio --temperatures 0.7 0.9 1.1 \
    --n-events 32 \
    --output-dir data/generated/v3
  ```
  Phase 2 work is largely **invoking** this script across 3 checkpoints,
  not modifying it.

- **`scripts/synthesize.py`** — handles soundfont resolution, FluidSynth
  subprocess invocation, and the EnCodec fallback chain. No changes needed.

- **`generate.py --eval` mode** — runs N samples at a single temperature
  and dumps aggregate event stats to JSON. Useful if quantitative metrics
  are wanted as supporting evidence (per D-01 these are optional context,
  not gating).

### Established Patterns

- **Per-checkpoint output dirs** — Plan 01-01 established `apollo_{run}` as
  the Modal-side checkpoint subdir naming. Mirror this client-side with
  `data/generated/{v2,v3,v4}/`.
- **`map_location='cpu'`** — Phase 1 Plan 03 confirmed this is required
  for `torch.load` on Mac. Already wired into `generate.py`.
- **GSD phase artifacts** — Phase 1 uses `{padded_phase}-{NN}-PLAN.md` and
  `{padded_phase}-{NN}-SUMMARY.md`. EVAL.md follows the same pattern as
  Phase 1's REVIEW.md / VERIFICATION.md.

### Integration Points

- WAVs land in `data/generated/{v2,v3,v4}/` — add this glob to `.gitignore`
  as part of Phase 2 (extends the existing `data/processed*/` ignore rules).
- EVAL.md scores reference WAV paths but the WAVs themselves are not in
  git — the markdown is the durable record.
- Downstream (Phase 3, OSC inference): the verdict from EVAL.md determines
  which checkpoint Phase 3 wires into `inference_server.py`. Today the
  default is v4 (streaming vocab), but if v4 scores below v3 on the
  rubric, Phase 3 may need to fall back to v3 with the base vocab.

### Creative Options

- `--bf16` + `--compile` give 2–4× decode speedup on Apple Silicon, which
  matters less for offline audio gen (27 short WAVs) but is worth a one-
  off correctness check now so Phase 3 can rely on them.
- v3's MelEncoder weights load but go unused at inference (the if-guard
  in `model.forward` skips mel when `mel_patch=None`). This means v3's
  evaluation tests "what v3 learned from mel-supervised training", not
  "v3 + live mel conditioning". The eval scores are the verdict on
  whether mel-supervised training is worth keeping.

</code_context>

<specifics>
## Specific Ideas

- The user's core concern (paused last session): "I do not feel like I've
  done my due diligence in ensuring the outputs are actually musical." The
  rubric + listen-test protocol is designed to answer this directly.
- v3 vs v2 comparison is the central scientific question: did mel
  conditioning during training transfer any musical benefit when mel is
  absent at inference? The val loss improvement (2.1641 → 2.1429) is a
  proxy; the rubric scores are the real answer.
- v4 has a known training shortfall; the eval will likely score it lower
  on phrase shape because at step 3,499 the model hasn't seen enough
  data to internalise long-range structure. Documenting this in EVAL.md
  is part of the deliverable.

</specifics>

<deferred>
## Deferred Ideas

### Architectural / Process

- **v4 fate decision** — re-train with tamed LR (3e-4, warmup_steps=2000)
  or accept the shortfall and proceed with v3 for Phase 3. Defer until
  EVAL.md scores are in — re-training is wasted compute if v4 scores
  fundamentally below v2/v3 on the rubric and the issue is the streaming
  representation itself rather than the LR.
- **Output storage policy beyond gitignore** — long-term retention of
  WAVs, manifest of best-of samples, audio commentary. Out of scope for
  this milestone; revisit at milestone-complete.
- **Mel patch generation at inference time** — would require synthesising
  the prompt MIDI to audio, extracting mel features, and feeding them in.
  Breaks the <10ms latency target. Deferred indefinitely or until a
  rolling-audio-input architecture is on the roadmap.
- **MIDI-prompted generation** (continuation from MAESTRO clip) — closer
  to the co-performance use case than BOS-only. Defer to Phase 3 where
  the OSC handler exercises this path live.
- **Multi-rater listening** — single scorer is fine for an internal
  milestone gate. If a public release is on the roadmap, revisit then.
- **Per-dimension anchor authoring** — D-03 calls for written anchors
  but the anchors themselves are best authored as the first task of
  Phase 2 execution, not pre-written here.

</deferred>

---

*Phase: 02-evaluation*
*Context gathered: 2026-05-19*
