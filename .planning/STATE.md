---
gsd_state_version: 1.0
milestone: v3.0
milestone_name: fm4synth canonical synth + local corpus-authoring app
status: roadmap_ready
stopped_at: v3.0 roadmap created (Phases 8–10). v2.0 (Phases 1–7) shipped and merged to main (PR #23). Next — /gsd-discuss-phase 8 or /gsd-plan-phase 8.
last_updated: "2026-06-02T00:00:00.000Z"
last_activity: 2026-06-02 — v3.0 roadmap created (Phase 8 engine swap → Phase 9 sequencer → Phase 10 app rework)
progress:
  total_phases: 3
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
  note: v2.0 shipped code-complete (Phases 1–7). v3.0 = Phases 8–10, roadmap ready, no plans written yet.
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-02)

**Core value:** Given a short MIDI call played through an FM patch, the model produces a response that feels like the user responding to themselves — and the active-learning loop demonstrably improves it over consecutive iterations.
**Current focus:** Phase 8 — Canonical Engine Swap (fm4synth): vendor the Rust engine, bump the FM spec to v2.0, rewrite the loader/validator, subprocess-render `call.wav`, remove the Faust path.

## Current Position

Milestone: v3.0 — fm4synth canonical synth + local corpus-authoring app
Phase: 8 of 10 (v3.0 spans Phases 8–10; continues numbering from v2.0's Phase 7)
Status: Roadmap ready — Phases 8–10 defined, no plans written yet.
Branch: gsd/phase-5-local-app-browser-synth (current working branch; start a v3.0/Phase-8 branch before planning)
Last activity: 2026-06-02

Carried context:
- v2.0 (Phases 1–7) shipped code-complete + merged to main (PR #23). Ship gate (EVAL-05: two consecutive improving held-out iterations) still unmet — depends on an authored corpus, which v3.0's authoring app exists to produce.
- v3.0 roadmap (Phases 8–10): Phase 8 = canonical engine swap (FM4-01..07); Phase 9 = 2-bar sequencer + MIDI staging (SEQ-01..04); Phase 10 = app rework + save-pair (APP-16..19). Strict order — 8 blocks 9 and 10; 10 depends on both.
- v3.0 supersedes Phase 6 (Faust renderer) + Phase 7 (Faust LFO) — implementation removed in Phase 8 (FM4-06). Canonical FM spec bumped to v2.0 = fm4synth's full 4-op + 4×4 matrix + multi-LFO model.
- Locked decisions (do NOT re-open): integration = vendor fm4synth + subprocess its Rust CLI via a MIDI+patch→score.json adapter (not a Python port, not WASM); browser synth is audition-only, canonical call.wav always server-rendered by Rust; corpus must be uniformly fm4synth-rendered — any Faust-trained checkpoint is void (retrain from scratch, acceptable since no corpus authored yet).
- Playground source: `/Users/jerald/Projects/playground/fm4synth` (Rust) + `fm4synth-ui` (Node+WebAudio).
- Deferred from Phase 5: 6 browser/audio human-UAT items (05-HUMAN-UAT.md) never run; moot for the parts v3.0 reworks (Phase 10), revisit for anything retained. One known-flaky Phase-7 test (test_lfo_pitch_depth0_matches_static) is superseded once the Faust LFO is removed (FM4-06).

Do NOT run /gsd-complete-milestone until EVAL-05 is satisfied.

## Performance Metrics

**Velocity:**

- Total plans completed: 6
- Average duration: ~7 min
- Total execution time: ~0.70 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01    | 5     | ~39m  | ~8m      |
| 02    | 5     | ~22m  | ~4.4m    |

**Recent Trend:**

- Last 7 plans: 01-01 (3.5m), 01-02 (~6m), 01-03 (12m), 01-04 (~5m), 01-05 (~12m), 02-01 (~5m), 02-02 (~2m)
- Trend: 02-02 was very fast — exact architecture spec from RESEARCH.md, one minor test fix (source-code check narrowed to nn.* prefix).

*Updated after each plan completion*
| Phase 05 P01 | 20m | 3 tasks | 9 files |
| Phase 05 P02 | ~4m | 3 tasks | 4 files |
| Phase 05 P03 | ~5m | 3 tasks | 6 files |
| Phase 05 P04 | ~6m | 3 tasks | 8 files |
| Phase 05 P05 | ~6m | 3 tasks | 8 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table and per-phase CONTEXT.md files.
Recent decisions affecting current work:

- Init: Train from scratch — no warm-start from prior checkpoint or MAESTRO pretrain
- Init: Vocab must reserve space for pitch bend / CC tokens so future additions don't break checkpoints
- Init: Mel encoder is jointly trained (not frozen pretrained); lives in the same checkpoint artifact
- Phase 1: Pitch vocab stays narrow (3 octaves, default C2–C5) — FM does the overtone work, not the MIDI model
- Phase 1: 32 quantized time bins, 16 velocity bins, explicit duration token (4 tokens/note)
- Phase 1: Mel = 22050 Hz, n_mels=128 / n_fft=2048 / hop=512, fixed-shape (96, 128)
- 01-01: Locked N_DURATION = 24 (log-spaced from 30 ms to 1.5 s); VOCAB_SIZE = 256 with 144 reserved tail slots
- 01-01: Corrected `quantize_time_shift` bin_width formula to `(60/bpm)*2/n_bins` (plan snippet had inconsistent `/8` formula)
- 01-04: Ordered empty-MIDI check before tempo check in load_notes — pretty_midi.estimate_tempo() raises on zero-note files
- 01-04: load_artifact uses weights_only=False (T-01-14 accept; trusted-local-only documented in module docstring)
- 01-04: discover_pairs path-traversal mitigation via Path.resolve() + relative_to(root_path) (T-01-11)
- 01-05: Mock pair default note durations = 0.5 s (quarter at 120 bpm) — 0.25 s tricks pretty_midi.estimate_tempo() into reporting 240 bpm and breaks the load_notes tempo guard
- 01-05: Default audio_seconds = 1.5 in synthesize_pair to cover three quarter notes
- 01-05: Phase 1 closed at 46/46 tests passing; 10-pair end-to-end ingest = 0.014 s on CPU (limit 10 s, 700× slack)
- 02-01: MelEncoder is a standalone nn.Module (not submodule of ApolloModel) per D-23/D-25 — separate state_dict keys at checkpoint time
- 02-01: Architecture locked to D-01 exactly: Conv2d(1→32)→ReLU→MaxPool×2→Conv2d(32→64)→ReLU→MaxPool×2→Conv2d(64→128)→ReLU→AdaptiveAvgPool→FC; 109,184 params confirmed
- 02-02: ApolloModel contains MelEncoder as submodule (self.mel_enc) — joint training via single model.parameters(); checkpoint saves mel_encoder_state_dict separately per D-23
- 02-02: pos_emb = nn.Embedding(max_seq_len+1, d_model) — size 65 for default max_seq_len=64 (RESEARCH pitfall #4 baked in)
- 02-02: Total params confirmed 976,384 (mel_enc 109,184 + tok_emb 32,768 + pos_emb 8,320 + transformer 793,088 + out_proj 33,024)
- 02-03: PAD_ID=0 reuses TIME_OFFSET=0 — pad_mask derived from sequence length L, never token_ids==0 (RESEARCH pitfall #1 baked into packer.py)
- 02-03: mel.unsqueeze(1) in collate_fn adds channel dim (B,1,96,128) required by Conv2d (RESEARCH pitfall #6)
- 02-03: tokens cast to int64 via .long() in collate_fn — artifact stores int32, nn.Embedding requires LongTensor
- 02-04: Loss mask boundary is j >= sep_pos (NOT j > sep_pos) — RESEARCH pitfall #2 confirmed via direct boundary test
- 02-04: train_epoch accepts scheduler=None as Phase 3 plug point — warmup+cosine injects without refactoring (D-16)
- 02-04: No torch.compile in train.py — not supported on MPS in PyTorch 2.8 (RESEARCH §4)
- 02-04: run_training uses AdamW(model.parameters()) — mel_enc covered via ApolloModel submodule, no separate instantiation needed
- 02-05: enable_nested_tensor=False on TransformerEncoder — disables MPS-incompatible nested tensor fast path (aten::_nested_tensor_from_mask_left_aligned raises NotImplementedError in eval mode with src_key_padding_mask)
- 02-05: load_checkpoint uses weights_only=False (D-24, trusted-local-only, documented in module docstring)
- 02-05: mel_encoder_state_dict saved as separate top-level key (D-23) via model.mel_enc.state_dict() — preserves Phase 3 independent loading option
- 02-05: Phase 2 closed: type_accuracy=1.0000 (gate >0.95), wall_clock=1.88s (budget 120s), checkpoint=3.7MB
- 06-01: A4 CLEARED — dawdreamer==0.8.3 + torch 2.12.0 import cleanly in one .venv (arm64/Py3.11); no venv isolation needed for 06-02/06-03
- 06-01: FM spec is the versioned single source of truth (SPEC_VERSION=1.0); engine consts SR=44100/BLOCK=512/NUM_VOICES=8/TARGET_PEAK=0.89 live in spec.py (determinism-critical)
- 06-01: 3 fixed algorithms — STACK(3→2→1), PARALLEL_MODS((2+3)→1), CARRIER_PAIR(3→1 + op2 carrier); all 3 dsp_string templates verified to compile in DawDreamer
- 06-01: Per-op slider naming = op{i}_ratio/level/attack/decay/sustain/release (i 1-based); render.py resolves names→indices at runtime via get_parameters_description() (no hardcoded indices — spike landmine)
- 06-01: Mono Faust output (single _); manifest validator rejects bools + NaN/Inf in numeric fields (T-06-01); ranges mirror Faust hslider ranges
- 06-02: ADSR is compiled as numeric literals inside en.adsr(...) — NOT runtime-settable sliders; only op{i}_ratio/level are runtime params (render.py sets only those by index). ADSR still takes effect (baked from manifest at compile time). Corrects the 06-01 slider-contract claim.
- 06-02: Unmangled slider name is in the DawDreamer description `label` field; `name` holds the mangled /Polyphonic/Voices/dawdreamer/<slider> path. Index map matches on label (trailing-path fallback).
- 06-02: render_call_wav(manifest_path, mid_path, *, pair_path, call_bpm, notes=None) is the SINGLE shared render path — generate.py (06-03) must call it with already-parsed call_notes + estimate_tempo() bpm so MIDI is parsed once and corpus/inference renders are bit-identical.
- 06-02: render_corpus enumerates pairs by call_fm.json+call.mid presence (NOT discover_pairs, which requires call.wav to pre-exist) — call.wav is a derived artifact.
- 06-02: Determinism confirmed np.array_equal True; peak after normalization = 0.89 (== TARGET_PEAK); timbre across contrasting presets cos 0.874 / L2 792 (matches spike 0.85/783)
- 06-03: Option A (render-only) — generate.py REMOVED the call.wav positional entirely (no --call-wav override); inference always renders call.wav from <pair_dir>/call_fm.json via the shared render_call_wav. Single inference code path = cleanest train/serve parity guarantee (T-06-12); no real caller passed a wav.
- 06-03: Single-parse pitfall avoided — call_bpm (estimate_tempo) + call_notes (load_notes) computed once before render; render_call_wav called with call_bpm=call_bpm AND notes=call_notes so the call MIDI is parsed exactly once, shared by render + tokenize.
- 06-03: Rendered audio array -> NamedTemporaryFile .wav at spec.SR -> frozen MelExtractor by path; mel (1,1,96,128) and all downstream sampling/decode/output-naming unchanged. IngestError (bad call_fm.json/MIDI) exits 1.
- 06-03: CORPUS-CONVENTIONS.md de-Ableton'd (authored = call.mid + call_fm.json + response.mid; call.wav derived/gitignored; render_corpus step + full call_fm.json schema documented; call_fm.json vs eval/render_manifest.py distinction noted; venv/bin -> .venv/bin). REQUIREMENTS DATA-01/02 marked superseded-by-DATA-06; DATA-06 done.
- [Phase ?]: _known_pairs_set checks call.mid+call_fm.json only (NOT discover_pairs) so pairs are enumerable before call.wav is rendered
- [Phase ?]: 05-01: host=127.0.0.1 in __main__.py only; create_app factory never binds (T-05-02)
- [Phase ?]: 05-01: TrainingJob uses Popen+daemon thread+line iteration; never communicate() (RESEARCH Pitfall 2)
- [Phase ?]: 05-01: spec_constants.js BOUNDS copied verbatim from manifest.py; dual client+server validation
- [Phase ?]: 05-02: synth.js hand-rolled Web Audio FM engine; no Tone.js; op_level*freq modulator amplitude (DX-style index); new OscillatorNode per note for LFO phase reset
- [Phase ?]: 05-02: attachLfo tremolo uses ConstantSource (DC offset) + scaled GainNode to drive carrier gainNode.gain; avoids AudioParam collision
- [Phase ?]: 05-02: /corpus iterates _known_pairs_set() only (never user-supplied nnn); patch embedded via |tojson in script[type=application/json] (T-05-04, T-05-05)
- [Phase ?]: 05-03: _allocate_next_nnn lock-guards find-max+mkdir (T-05-07 race); partial dirs removed via shutil.rmtree on IngestError (Pitfall 5)
- [Phase ?]: 05-03: render() called with in-memory FmParams+notes (not render_call_wav); avoids re-reading just-written files
- [Phase ?]: 05-03: threading.Timer 3.0s debounce for auto-retrain; _debounce dict avoids closure assignment issues
- [Phase ?]: 05-03: drawLossCurve strokes train_loss solid #6D28D9, held_loss dashed #15803D on Canvas 2D
- [Phase ?]: 05-04: lfo key omitted entirely when editor LFO checkbox is unchecked (absent = v1.0-identical render per spec.py)
- [Phase ?]: 05-04: _latest_checkpoint uses max(mtime) over models/*.pt (RESEARCH OQ2); response_\d+\.mid allow-list uses module-level anchored regex _RESPONSE_FILENAME_RE
- [Phase ?]: 05-04: /generate subprocess argv is fixed list ['python', '-m', 'apollo.scripts.generate', ckpt, call.mid] — no shell=True, no user strings (T-05-14)
- [Phase ?]: 05-05: registry is app-layer only; train.py/generate.py UNCHANGED; CLI training produces checkpoints but not registry rows (accepted v1 limitation)
- [Phase ?]: 05-05: _active_checkpoint: pin wins if file exists, stale pin falls to _latest_checkpoint, ACTIVE-unset == latest-by-mtime (D-06)
- [Phase ?]: 05-05: corpus_hash is content-flag only (SEED-011 defers snapshotting); POST /models/activate uses fixed-set membership guard (T-05-17, mirrors _validate_pair_nnn)
- [Phase ?]: 05-05: append_run never moves ACTIVE; pin survives retrains until user re-activates (D-06)
- v3.0 (locked at milestone kickoff): integration = vendor fm4synth + subprocess Rust CLI via MIDI+patch→score.json adapter (NOT a Python port, NOT WASM); canonical FM spec → v2.0 (fm4synth's full 4-op + 4×4 matrix + multi-LFO, no trim); browser synth audition-only, canonical call.wav ALWAYS server-rendered by Rust; corpus uniformly fm4synth-rendered, any Faust-trained checkpoint void (retrain from scratch — acceptable, no corpus authored yet).

### Pending Todos

None yet.

### Blockers/Concerns

None yet.

### Roadmap Evolution

- 2026-06-02: **v3.0 roadmap created — Phases 8–10.** Milestone v3.0 (fm4synth canonical synth + local corpus-authoring app) continues numbering from v2.0's Phase 7. Phase 8 (Canonical Engine Swap): vendor `fm4synth` Rust engine, bump FM spec → v2.0 (4-op + 4×4 matrix + multi-LFO), rewrite `call_fm.json` loader/validator, subprocess-render `call.wav` via a MIDI+patch→score.json adapter, remove the Faust/DawDreamer + v1.1-LFO path (FM4-01..07). Phase 9 (2-Bar Sequencer & MIDI Staging): 2-bar quantized piano-roll, separate call/response staging, `load_notes`-valid `.mid` export, in-browser audition (SEQ-01..04). Phase 10 (Authoring App Rework & Save-Pair): retarget app editor + browser preview to 4-op fm4synth, Save-pair flow (staged sequences + patch → `data/pairs/NNN/` + server-rendered `call.wav`), keep corpus/train/generate/registry flows working (APP-16..19). Strict order: 8 → 9 → 10 (8 blocks both; 10 depends on both). Supersedes Phase 6 (Faust renderer) + Phase 7 (Faust LFO) — implementation removed in Phase 8. Coverage: 15/15 v3.0 reqs mapped, 0 unmapped, none duplicated.
- 2026-06-02: Phase 7 added — Synth Automation (LFO). Promotes the call-side half of backlog 999.2: a deterministic per-patch LFO on the owned FM synth (FM spec → v1.1, backward-compatible with v1.0 manifests), mirrored by Phase 5's browser synth. New requirement SYNTH-01. Lets a call's timbre/pitch evolve over a note (the rhythmic/timbral motion FM is known for) — the expression mechanism a future response-side model (EXPR-02 / 999.2b) would learn to answer. Also fixed WR-01 (silent renders no longer amplified to full-scale noise; 177 tests). *(v3.0 supersedes: the v1.1 Faust LFO is subsumed by fm4synth's native multi-LFO model — implementation removed in Phase 8.)*
- 2026-06-02: Phase 6 added & planned — Synth-Independent Corpus Rendering. Drops Ableton/Operator: an owned headless Python FM synth (DawDreamer + Faust, 3-op) renders `call.wav` deterministically from a per-pair FM-param manifest, feeding the unchanged MelExtractor (COND-01). New requirement DATA-06; supersedes the manual-bounce premise of DATA-01/02. Prerequisite for DATA-05 corpus authoring. Defines the single FM spec that Phase 5's browser synth consumes. Backed by /gsd-explore decision (.planning/notes/synth-independence-decision.md) + spikes 001/002 (packaged as the spike-findings-apollo skill). Deferred: full 4-op/11-algorithm engine → SEED-009. *(v3.0 supersedes: the Faust/DawDreamer renderer is replaced by the vendored fm4synth Rust engine — removed in Phase 8; the single-source-of-truth spec concept survives, bumped to v2.0.)*
- 2026-06-01: Phase 5 added — Local App & In-Browser Synth. Purely local user-facing app: drag-drop pair ingest, corpus-growth flow, in-browser Operator-style FM synth (Web Audio, removes manual Ableton bounce), manual + auto-retrain triggers, configurable response storage, call→response flow. New requirements (candidate APP-*) to be authored at plan time. *(v3.0 reworks: Phase 10 retargets the editor + browser preview to the 4-op fm4synth model and adds the sequencer-fed Save-pair flow.)*

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| *(none)* | | | |

## Session Continuity

Last session: 2026-06-02T00:00:00.000Z
Stopped at: v3.0 roadmap created (Phases 8–10). ROADMAP.md, REQUIREMENTS.md traceability, and STATE.md updated.

Resume:

- v3.0 roadmap ready. Next: `/gsd-discuss-phase 8` (recommended) or `/gsd-plan-phase 8` to start the canonical engine swap. Run `/gsd-progress` for a full status overview.
- Start a v3.0 / Phase-8 branch before planning (current branch is `gsd/phase-5-local-app-browser-synth`; v2.0 is merged to main).

Mock UAT fixture on disk: `data/pairs/000..019` (5 held-out: 006, 009, 010, 012, 019) + `eval/scores.jsonl` partially filled. Delete before authoring real corpus (note: these are Faust-era renders — void under the fm4synth engine swap).
