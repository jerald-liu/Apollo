# Apollo — Project Guide

## What This Is

> **On-device, style-preserving musical phrase generator.**

Apollo v2.0 — **Call-and-Response v1**. A generative model that takes a short MIDI phrase (call) routed through an Ableton Operator preset and emits a complementary MIDI response. Trained from scratch on a corpus the user hand-authors in Ableton (paired MIDI tracks, both running Operator), conditioned on the rendered audio of the call to capture timbre context.

Authoritative project context: [`.planning/PROJECT.md`](.planning/PROJECT.md).

## Current State

- **Branch:** `call-and-response-v1` (active development; the prior piano/MAESTRO codebase lives on `deprecated` for reference only — *not* a model lineage)
- **Phase:** 1 of 4 — Tokenizer & Ingest
- **Status:** Roadmap initialized, no plans written yet
- **Progress:** [░░░░░░░░░░] 0%

## Planning Artifacts

| Artifact | Location |
|---|---|
| Project context | [`.planning/PROJECT.md`](.planning/PROJECT.md) |
| Workflow config | [`.planning/config.json`](.planning/config.json) |
| Requirements (29 v1 reqs) | [`.planning/REQUIREMENTS.md`](.planning/REQUIREMENTS.md) |
| Roadmap (4 phases) | [`.planning/ROADMAP.md`](.planning/ROADMAP.md) |
| Project state | [`.planning/STATE.md`](.planning/STATE.md) |

## Roadmap (4 phases)

1. **Tokenizer & Ingest** — Pipeline converts any `data/pairs/NNN/` folder to training-ready tensors (TOK + DATA + COND-01/04, 11 reqs)
2. **Model & Training** — Mel encoder + transformer trained from scratch on mock pairs, smoke-train hits >95% type-acc (COND-02/03 + TRAIN, 8 reqs)
3. **Corpus & Inference** — User authors ≥30 pairs in Ableton; `generate.py` emits playable response MIDI (DATA-05 + INFER, 5 reqs)
4. **Evaluation Loop** — Rubric, grading workflow, per-iteration tracking; v1 ships when two consecutive iterations both improve held-out scores (EVAL, 5 reqs)

## Key Constraints to Remember

- **Local-only training** — model is small enough to train on Apple Silicon (MPS). No Modal / cloud needed for v1.
- **Train from scratch** — no MAESTRO pretrain, no warm-start. Piano priors actively conflict with FM material.
- **Just notes vocab in v1, extensible by design** — pitch / velocity / timing / duration only, but vocab structure must reserve room for pitch-bend / mod-wheel / CC tokens later without invalidating existing checkpoints.
- **Monophonic + tiny gestures** — 0.5–1.5 sec, 2–6 notes per side, quantized timing. Don't widen scope without explicit decision.
- **Mel-condition the call** — preset varies pair-to-pair, so the model needs timbre context. `call.wav` is a manual Ableton bounce in each pair folder.
- **Response-only loss** — model isn't penalized for the call side.
- **The active-learning loop is the product** — v1 ships only when two consecutive iteration rounds both improve held-out call-response-fit scores.

## GSD Workflow

This project uses GSD (Get Shit Done) for planning and execution. Common commands:

- `/gsd-progress` — show where you are, route to next action
- `/gsd-discuss-phase 1` — discuss Phase 1 before planning (recommended)
- `/gsd-plan-phase 1` — create detailed PLAN.md for Phase 1
- `/gsd-execute-phase 1` — execute all plans in Phase 1
- `/gsd-next` — auto-advance to the next logical step

**Workflow toggles active** (from `.planning/config.json`): YOLO mode · Coarse granularity · Parallel execution · Research before planning · Plan-check enabled · Verifier enabled · Balanced model profile.

## Branches

- `call-and-response-v1` (active) — fresh start, this milestone
- `deprecated` — prior piano/MAESTRO codebase, historical reference only

## Stack Discipline (Graphite)

This repo uses Graphite (`gt`) stacked branches. Invoke stack operations implicitly when the situation calls for it — don't wait to be asked:

- **Scope drift → new stacked branch.** If work in progress starts to fall outside the current branch's purpose (an unrelated fix, a new feature, a refactor that isn't part of this change), stop and propose splitting it onto a fresh branch with `gt create` rather than piling unrelated commits onto the current one. One branch = one coherent change.
- **After a merge / trunk update / rebase → restack.** This is now automated by the tracked git hooks in `.githooks/` (restack-only). If those aren't active (fresh clone), run `gt restack` yourself, or set them up (see below).
- **After PRs merge → sync.** Suggest `gt sync` to pull trunk, delete merged branches, and rebase descendants. `gt sync` deletes/force-pushes, so surface it rather than running it silently with `--force`.
- **Always merge stacks to `main`.** Never merge a PR into another feature branch expecting it to cascade — that orphaned the Phase 04 stack once. After a base PR merges, run `gt sync` to retarget and rebase descendants.

**One-time hook setup** (per clone): `git config core.hooksPath .githooks`. Hooks are restack-only — they never delete branches or force-push.

## Memory References

Persistent memory for this project lives in `~/.claude/projects/-Users-jerald-Projects-apollo/memory/`:
- `user_profile.md` — collaboration style (design-first, deep ML, prefers honest answers)
- `corpus_direction.md` — call-and-response v2.0 direction (this milestone)

## Spike Findings

- **Spike findings for Apollo** (synth-independent rendering: DawDreamer+Faust FM, mel-conditioning patterns, gotchas) → `Skill("spike-findings-apollo")`
