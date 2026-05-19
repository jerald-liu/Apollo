# Phase 1: Tokenizer & Ingest - Context

**Gathered:** 2026-05-19
**Status:** Ready for planning

<domain>
## Phase Boundary

The symbolic pipeline. The deliverable is the conversion layer that takes any `data/pairs/NNN/{call.mid, call.wav, response.mid}` folder and produces training-ready tensors: a tokenized MIDI sequence for the call, a tokenized MIDI sequence for the response, and a fixed-shape mel-spectrogram tensor of the call audio.

**Out of this phase:** the model, the training loop, augmentation, inference, evaluation, and the act of authoring corpus pairs in Ableton. Those are Phases 2–4.

</domain>

<decisions>
## Implementation Decisions

### Tokenizer — pitch vocab
- **D-01:** Pitch vocab covers a 3-octave window — **37 pitches** (12 × 3 + 1 to include both endpoints).
- **D-02:** Default window is **C2–C5 (MIDI 36–72)** for v1. The user explicitly deferred the exact window — author the corpus, see what the music actually uses, widen or shift later if needed.
- **D-03:** "Screeches" / high overtone content is **not** modeled as high MIDI pitches. FM does the overtone work via timbre/preset (carried by mel conditioning). The model stays in a narrow pitch band; loudness/brightness lives in the audio side. This is architecturally load-bearing — do not widen pitch range without revisiting this decision.
- **D-04:** MIDI notes outside the 37-pitch window during ingest cause the pipeline to **abort with the offending pair identified** (same error policy as missing audio per COND-04). No silent clipping or wraparound — that would smuggle in pitch errors the user can't see.

### Tokenizer — time/velocity/duration
- **D-05:** Time-shift is encoded with **32 quantized-grid bins** (one bin per 32nd-note over ~2 beats at the corpus tempo). Strictly quantized — no log spacing, no off-grid bins in v1.
- **D-06:** Velocity is encoded with **16 linear bins** (4-bit resolution).
- **D-07:** Duration is encoded as an **explicit duration token per note** (not note-on/note-off pairs, not implicit fixed duration). Per-note token packing is `[time_shift, pitch, velocity, duration]` = **4 tokens per note**.
- **D-08:** Per-side token packing for the model uses the full `[BOS, call_tokens, SEP, response_tokens, EOS]` layout from REQUIREMENTS TRAIN-01 — but the SEP/BOS/EOS wrapping happens at the **training packer**, not in the tokenizer. The tokenizer's per-pair output is just the raw note-event sequence; the wrapping is the next phase's concern. (Tokenizer must still **define** the IDs for BOS/EOS/SEP — see D-10.)

### Tokenizer — vocab layout & extensibility
- **D-09:** Vocab uses **contiguous reserved-tail-slots** for future expression tokens (TOK-04). v1 packs the active vocab into IDs 0..N-1; pitch bend / mod wheel / CC tokens will occupy IDs N..(N+K-1) when added in v2. Existing v1 checkpoints remain valid because the new IDs are guaranteed not to collide with anything in 0..N-1.
- **D-10:** Vocab structure (concrete IDs to be finalized in planning, but the order is):
  ```
  [0 .. 31]    time_shift tokens     (32 bins)
  [32 .. 68]   pitch tokens          (37 pitches, C2–C5 default)
  [69 .. 84]   velocity tokens       (16 bins)
  [85 .. ...]  duration tokens       (count TBD in planning; suggest 16–32 log-spaced bins from 30ms to 1.5s)
  [...]        BOS, EOS, SEP         (3 special tokens)
  [reserved]   pitch_bend, mod_wheel, CC tokens (allocated but unused in v1)
  ```
  Total active v1 vocab ≈ 100–120 IDs depending on duration bin count. Generously, reserve through ~256 for v2 expression.

### Mel — features
- **D-11:** Sample rate **22050 Hz** for `call.wav` ingest. Downsample from Ableton's 44.1/48 kHz output. Nyquist 11kHz captures musically-relevant FM harmonics; doubling SR would double audio-side compute for no demonstrated benefit.
- **D-12:** Mel preset: **n_mels=128, n_fft=2048, hop_length=512**. Standard music-information-retrieval defaults. At 22050 Hz this gives ~43 frames/sec.
- **D-13:** **Fixed-shape mel tensor** going into the encoder. Each call's mel is padded (or truncated, rare in v1) to **96 frames × 128 mels**. 96 frames at 43 fps ≈ 2.23 sec — gives ~50% headroom over the 1.5s max gesture length so authoring drift up to ~2.2s doesn't break the pipeline.
- **D-14:** Mel feature shape is part of the tokenizer/ingest contract — Phase 2's mel encoder must accept exactly `(B, 96, 128)`. If we later widen call length, the fixed shape changes and existing checkpoints become invalid; document this as a hyperparameter, not a data property.

### Pair ingest — pipeline behavior
- **D-15:** The ingest function takes a `data/pairs/` root, scans for `NNN/` subdirectories, and for each pair: parses `call.mid` → tokens, loads `call.wav` → mel tensor (per D-11/12/13), parses `response.mid` → tokens. Returns a structured dataset object (exact return type TBD in planning, but it must be deterministic across runs given the same input).
- **D-16:** Missing or malformed `call.wav` → **abort with offending pair path printed** (REQUIREMENTS COND-04). Same policy for missing `call.mid` or `response.mid` even though that's not literally in REQUIREMENTS — the contract is "no silent skipping anywhere."
- **D-17:** Pair NNN gaps (e.g. pairs 1, 2, 4 with no 3) are **allowed** — pairs are addressed by their actual NNN, not by sequence position. The 20% held-out split is computed over the set of NNNs that actually exist.

### Storage format (Claude's Discretion / locked default)
- **D-18:** Pre-tokenize all pairs once into a single artifact (e.g. a `.pt` file containing tokens, mel tensors, and metadata). Re-run ingest when the corpus changes. This avoids re-parsing MIDI / recomputing mel every training step.
- **D-19:** The DataLoader for training reads from the pre-tokenized artifact, not from disk per step.

### Held-out split (Claude's Discretion / locked default)
- **D-20:** Hash-based deterministic 20% split — `int(hashlib.sha1(NNN_string).hexdigest(), 16) % 5 == 0` → held out. Same NNN always lands in the same split regardless of authoring order or new pair additions. Robust against the corpus growing mid-iteration.

### Claude's Discretion (other)
- **D-21:** Exact duration bin count and bin edges (within the 16–32 range hinted in D-10).
- **D-22:** Concrete file paths and Python module structure for the ingest pipeline.
- **D-23:** Any normalisation applied to mel features (per-sample log + clip, or per-corpus mean/std). Default to log-mel without further normalisation; revisit if training Phase 2 surfaces instability.

</decisions>

<specifics>
## Specific Ideas

- The user explicitly framed pitch range as narrow + "screeches as overtones": **the model stays in 3 octaves, FM does the brightness**. This is the design's most distinctive choice and downstream agents must respect it.
- "Quantized for now, groove/free timing later" — the time-shift vocab is grid-locked in v1. The reserved-tail-slots extensibility scheme is how that migration happens without invalidating checkpoints.
- The user wants to author the corpus before locking the exact pitch window. C2–C5 is a placeholder default; expect it to move.

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project context
- `.planning/PROJECT.md` — Apollo v2.0 scope, core value, requirements section (Active/Out-of-Scope), Key Decisions table
- `.planning/REQUIREMENTS.md` §`v1 Requirements / Tokenizer (TOK)` — TOK-01 to TOK-05 (vocab structure, BOS/EOS/SEP, round-trip test, extensibility)
- `.planning/REQUIREMENTS.md` §`v1 Requirements / Corpus (DATA)` — DATA-01 to DATA-04 (folder layout, ingest, held-out split)
- `.planning/REQUIREMENTS.md` §`v1 Requirements / Audio Conditioning (COND)` — COND-01, COND-04 (mel extraction, missing-audio abort policy)
- `.planning/ROADMAP.md` §`Phase 1: Tokenizer & Ingest` — Goal and 5 success criteria

### Branch/codebase context
- `CLAUDE.md` — Current state pointers and constraint summary
- The `deprecated` branch is **reference only** — do NOT plan to reuse `src/representation.py`, `src/streaming_representation.py`, `src/spectral.py`, or any of the prior piano-era code. Phase 1 builds from scratch on `call-and-response-v1`.

No external ADRs or design docs exist for this project — decisions captured here are the source of truth.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- None — the active branch (`call-and-response-v1`) is an orphan with only `CLAUDE.md`, `README.md`, `.gitignore`. No source code exists yet.
- The `deprecated` branch contains prior implementations (`src/representation.py`, `src/spectral.py`, etc.) that **may inform design** but are not to be imported or copied wholesale. Piano-specific assumptions are baked deep into that code; cherry-picking pieces will reintroduce the assumptions.

### Established Patterns
- No patterns established yet — this is the first feature on the new branch.
- Future phases will likely standardise on PyTorch tensors as the internal data contract; Phase 1's output shape choices (token integer arrays + mel `(96, 128)` floats) set the precedent.

### Integration Points
- The ingest pipeline's output is the input to Phase 2's training loop. The contract between phases is the pre-tokenized artifact format (D-18). That artifact format is the API boundary — pin it explicitly in the plan.
- `data/pairs/NNN/` folder convention (DATA-02) is consumed by the ingest function and produced by the user authoring in Ableton. The ingest must validate the convention strictly (D-16).

</code_context>

<deferred>
## Deferred Ideas

- **Exact 3-octave pitch window** — author the corpus with C2–C5 as a placeholder, then revisit. May shift down for bass-heavy material or up for melodic-lead material. Not a Phase 1 blocker.
- **Pitch-shift augmentation** — out of this phase entirely. Augmentation that pitch-shifts MIDI must also pitch-shift the call audio to keep mel features aligned. Belongs in Phase 2 (training) discussion.
- **Pitch bend / mod wheel / CC tokens** — vocab slots are reserved (D-09) but no encoding/decoding logic written. Phase 1 does *not* implement them; the reservation is the only Phase 1 cost.
- **Groove / free / off-grid timing tokens** — same: reserved at the architecture level, not implemented.
- **Variable-length mel input** — fixed-shape is locked for v1 (D-13). Variable + masked attention is a future option if 96-frame truncation ever bites.
- **Mel normalisation strategy beyond log-mel** — defer to Phase 2 if training instability shows up.

</deferred>

---

*Phase: 01-tokenizer-ingest*
*Context gathered: 2026-05-19*
