---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: milestone
status: code_complete_corpus_pending
stopped_at: All 4 phases executed & verified (Phase 04 UAT 12/12 pass). Ship gate blocked on human corpus authoring (DATA-05) + iteration loop (EVAL-05).
last_updated: "2026-05-31T00:00:00Z"
last_activity: 2026-05-31 -- Reconciled stale STATE; deleted mock UAT fixtures (data/pairs/000..019, eval/scores.jsonl, eval/runs.jsonl, render manifest, UAT checkpoint) ahead of real corpus authoring
progress:
  total_phases: 4
  completed_phases: 4
  total_plans: 17
  completed_plans: 17
  percent: 100
  note: percent is code-side only; v1 ship gate (DATA-05 ≥30 pairs, EVAL-05 two consecutive improving iterations) is unmet
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-19)

**Core value:** Given a short MIDI call played through an Operator preset, the model produces a response that feels like the user responding to themselves — and the active-learning loop demonstrably improves it over consecutive iterations.
**Current focus:** Phase 04 — evaluation-loop (executed; corpus authoring still required for v1 ship gate)

## Current Position

Phase: 04 (evaluation-loop) — Executed & verified (UAT 12/12)
Plan: 4 of 4 (all complete)
Status: All 4 phases code-complete — rubric, eval library, CLIs, grading UI shipped; 159/159 tests passing. Mock UAT fixtures deleted 2026-05-31.
Last activity: 2026-05-31

Progress: [██████████] 100% code-side — but v1 is NOT shippable yet.
Open ship-gate dependencies (both require the human-in-the-loop, no GSD coding command):
- DATA-05: author ≥30 call/response pairs in Ableton (data/pairs/), each with call.wav bounce
- First real training run (train.py) + first eval iteration (generate → blind-grade in Flask UI)
- EVAL-05: two consecutive iteration rounds must both improve mean held-out call-response-fit score
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

### Pending Todos

None yet.

### Blockers/Concerns

None yet.

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| *(none)* | | | |

## Session Continuity

Last session: 2026-05-23T16:00:00Z
Stopped at: Phase 04 UAT paused after test 9/12. Two real bugs found and fixed inline (PR #17 commit 99d8af9); one cosmetic issue still open (reveal aside newlines). Tests 10–12 require setup (a real checkpoint + response_001.mid in each held-out pair) — full instructions in `.planning/phases/04-evaluation-loop/04-UAT.md` §Resume Notes.

Resume:
- `/gsd-verify-work 4` to continue UAT from test 10
- Or `/gsd-progress` for a full status overview
- Working branch: `phase-04-fix-grading-ui` (PR #17, stacked on #16)
- Open cosmetic UAT issue: `.mono` CSS needs `white-space: pre-wrap` for reveal aside newlines (apollo/eval/web/static/style.css)

Mock UAT fixture on disk: `data/pairs/000..019` (5 held-out: 006, 009, 010, 012, 019) + `eval/scores.jsonl` partially filled. Delete before authoring real corpus.
