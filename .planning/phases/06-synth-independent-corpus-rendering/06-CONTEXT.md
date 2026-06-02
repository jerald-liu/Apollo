# Phase 6: Synth-Independent Corpus Rendering - Context

**Gathered:** 2026-06-02
**Status:** Ready for planning
**Source:** Explore session (`/gsd-explore`) — see `.planning/notes/synth-independence-decision.md`. The explore session served as the design discussion for this phase; decisions below are locked.

<domain>
## Phase Boundary

Replace the manual Ableton/Operator `call.wav` bounce with an **owned FM synth rendered headlessly in Python** (DawDreamer + Faust). This phase delivers:
1. A single **source-of-truth FM spec** (parameter schema + algorithm set + envelope semantics).
2. A deterministic **3-operator** Faust renderer (via DawDreamer) that turns `call.mid` + a per-pair FM-param manifest into `call.wav`.
3. Wiring so the **same engine renders inference-time calls** (train/serve parity).
4. Updates to corpus conventions / requirements that remove the Ableton-bounce premise.

**In scope:** the headless Python renderer, the FM spec/manifest format, determinism + normalization, integration with the existing `MelExtractor` (COND-01), and doc/requirement updates.

**Out of scope:** Operator sound-fidelity cloning (explicitly rejected); the Phase 5 browser synth implementation (Phase 6 only *defines the spec* it will later consume); the full 4-op/11-algorithm engine (deferred — `SEED-009`); model changes.
</domain>

<decisions>
## Implementation Decisions (LOCKED)

### Synth engine
- Use **DawDreamer + Faust** for headless rendering. Validated in spikes 001/002 (`dawdreamer==0.8.3` arm64 wheel, deterministic Faust FM render).
- v1 engine is **3 operators** (not 4). Full 4-op/11-algorithm/filter/LFO topology is deferred to `SEED-009`.
- **Do NOT clone Operator's sound.** Provide a controllable FM family only. Operator's character was judged incidental.

### Timbre authoring
- Per-pair timbre is a **hand-authored FM-param manifest** (JSON or code) — no synth UI for v1 (that's Phase 5's job).
- The manifest format + FM parameter schema + algorithm set + envelope semantics live in **one place** (single source of truth) so the Phase 5 browser synth can later implement the same spec.

### Determinism & integration
- Rendering must be **bit-deterministic**: same manifest + MIDI → identical `call.wav`.
- Rendered audio must feed the existing `apollo/ingest/audio.py` `MelExtractor` (COND-01) **unchanged** to its `(96,128)` contract. No pipeline changes downstream.
- **Same engine + manifest format render inference-time calls** (train/serve parity — no domain gap).
- Apply **normalization / headroom** before writing PCM (spike 001 saw peaks >1.0 that `soundfile` clips).

### Docs / requirements to reconcile
- Update `data/pairs/CORPUS-CONVENTIONS.md` authoring workflow (currently Ableton-bounce steps + D-02 "Operator preset") to the FM-manifest workflow.
- Amend `REQUIREMENTS.md` DATA-01 / DATA-02 wording (they still say "author in Ableton" / "manual Ableton bounce") — superseded by DATA-06.
- This phase **blocks DATA-05** (real corpus authoring) — must land before authoring resumes.

### Build gotchas (from `spike-findings-apollo` skill — MUST honor)
- Faust polyphony params: set via **integer index**, not path string.
- Filter the benign `undefined symbol : effect` warning.
- `dawdreamer.__version__` does not exist.

### Claude's Discretion
- Exact manifest JSON schema fields and the FM parameter set within the 3-op envelope (within "small + hand-authorable").
- Where the FM spec module lives in `apollo/` and the render CLI surface/name.
- How `call.mid` is parsed into note events for DawDreamer (likely via existing `apollo/ingest/midi.py` or `pretty_midi`) and render sample rate (renderer SR is free; `MelExtractor` resamples to 22050).
- Reuse vs. extension of existing `apollo/eval/render_manifest.py` naming concepts (distinct purpose — that's the M4L eval manifest; avoid confusion).
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Decision & requirements
- `.planning/notes/synth-independence-decision.md` — the locked decision + rationale + Phase 5 reconciliation
- `.planning/REQUIREMENTS.md` — DATA-06 (this phase), COND-01 (the mel contract), DATA-01/02 (to amend)
- `.planning/ROADMAP.md` — Phase 6 block (goal + success criteria), Phase 5 cross-phase note

### Code to integrate with / mirror
- `apollo/ingest/audio.py` — `MelExtractor`, the COND-01 contract the rendered wav must satisfy (22050 Hz, n_fft=2048, hop=512, n_mels=128, fixed (96,128))
- `apollo/ingest/midi.py` — existing MIDI loading (`load_notes`, 120 BPM ±2 tolerance per D-01)
- `apollo/ingest/errors.py` — `IngestError` pattern for fail-loud reporting
- `data/pairs/CORPUS-CONVENTIONS.md` — corpus layout + authoring conventions to update

### Validated patterns (project skill)
- `.claude/skills/spike-findings-apollo/SKILL.md` + `references/synth-independent-rendering.md` — working DawDreamer+Faust render code, mel-check code, and build landmines
- `.planning/spikes/001-dawdreamer-fm-render/`, `.planning/spikes/002-fm-mel-conditioning/` — runnable spike sources
</canonical_refs>

<specifics>
## Specific Ideas
- The spike's 2-op Faust patch + integer-index param setting + `add_midi_note` loop + `render()` + `soundfile.write(audio.T)` is the proven skeleton — extend to 3-op with a documented param schema.
- Determinism check pattern from spike 001 (`np.array_equal` on re-render) is a good acceptance test.
- Mel-equivalence check from spike 002 (rendered wav → `MelExtractor` → (96,128), timbre-discriminable) is a good integration test.
</specifics>

<deferred>
## Deferred Ideas
- Full 4-op / 11-algorithm / filter / LFO engine → `SEED-009`.
- Phase 5 browser-synth implementation of the shared spec → Phase 5.
- FM patch generation head (model outputs timbre) → `SEED-001` / backlog 999.1.
</deferred>

---

*Phase: 06-synth-independent-corpus-rendering*
*Context gathered: 2026-06-02 via /gsd-explore decision record*
