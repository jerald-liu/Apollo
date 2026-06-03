---
id: SEED-011
status: dormant
planted: 2026-06-02
planted_during: v2.0 / Phase 05 (local-app-browser-synth) planning
trigger_when: When model version-history / rollback exists and users need to reproduce or trust a past run; OR when a changed corpus has invalidated old checkpoints; OR a milestone focused on reproducibility / provenance / experiment tracking
scope: Medium
---

# SEED-011: Corpus snapshotting for true training reproducibility + checkpoint retention

Phase 5 (Plan 05-05) gives Apollo **model version-history + rollback**: an append-only `models/runs.jsonl` registry and an active-model pointer let a user pin/revert to any prior `run-{iter}-{ts}.pt`. That makes *model* rollback real. This seed covers the deeper guarantee it does NOT yet provide: **reproducibility of a run against the data it was trained on.**

## Why This Matters

Every Apollo train is **from-scratch on the whole corpus** (D-05). So the true lineage is **corpus-snapshot → model**, never model → model. Consequences:

- If a user rolls the *model* back but the corpus has changed since, the old checkpoint no longer corresponds to their current data. The rollback is silently "stale."
- "Why did iteration 7 score worse than iteration 6?" is unanswerable without knowing *which pairs existed* at each run. The eval loop (EVAL-05: two consecutive improving iterations) is a comparison across runs — its validity rests on knowing the data each run saw.
- v1's mitigation (from Plan 05-05) is shallow: `runs.jsonl` records a **corpus hash + pair count** per run, enough only to *flag* "this model was trained on a different corpus than you have now." It cannot *reconstruct* the corpus.

True reproducibility wants the data itself versioned alongside the model.

## What This Seed Proposes

- **Corpus snapshotting per run:** capture the exact set of pairs (content-addressed: per-pair hash of `call.mid` + `call_fm.json` + `response.mid`) at train time, so any historical run can be reconstructed or diffed against the current corpus. Options range from a manifest of hashes (cheap, no data copy) to a content-addressed store / git-style snapshot of `data/pairs/` (heavier, fully reconstructable).
- **Run ↔ corpus-snapshot ↔ eval-score linkage:** one provenance chain so the app can show "iteration 6 (24 pairs) → iteration 7 (+3 pairs) → score moved from X to Y," directly serving the active-learning loop's improvement story.
- **Checkpoint retention policy:** checkpoints are tiny (~3.7 MB each), so history is cheap, but a "keep last N + keep all eval-graded + keep all pinned" pruning setting is a natural addition once history grows.

## When to Surface

**Trigger:** rollback exists and the corpus-hash flag (Plan 05-05) starts mattering — i.e., users hit stale rollbacks, or the eval loop needs per-run data provenance to explain score changes. Also any milestone scoped around reproducibility, experiment tracking, or provenance.

Present during `/gsd-new-milestone` when scope matches:
- "reproduce / audit / trust a past training run"
- "the corpus changed and old checkpoints no longer match"
- "explain why one iteration scored better/worse than another"
- "experiment tracking / provenance / data versioning"
- "checkpoint retention / disk management"

## Scope Estimate

**Medium** — a phase. A hash-manifest-per-run approach is modest (content hashing + registry extension + a diff view); a full content-addressed corpus store is larger. Retention policy is small on top.

## Breadcrumbs

- `apollo/scripts/train.py` — from-scratch retrain on the whole corpus (D-05); writes `models/run-{iteration:02d}-{timestamp}.pt` (D-10); each checkpoint embeds `training_meta`.
- `models/runs.jsonl` (introduced by Phase 5 Plan **05-05**, req **APP-14**) — the registry this seed deepens; already records corpus size + hash per run. The active-model pointer + rollback UI is **APP-15**.
- `apollo/scripts/generate.py` (positional `checkpoint` arg) — consumes a specific checkpoint; reproducibility would let it also pin the matching corpus snapshot.
- `eval/runs.jsonl` / `eval/scores.jsonl` — existing append-only-log precedent; the run↔score linkage extends this pattern.
- `data/pairs/` + `data/pairs/CORPUS-CONVENTIONS.md` — the corpus to snapshot (a pair = `call.mid` + `call_fm.json` + derived `call.wav` + `response.mid`).
- **Related seeds:** `SEED-007-training-sufficiency-diversity-metrics.md` (corpus diversity/sufficiency — shares the per-run corpus-provenance substrate).

## Notes

Discussed 2026-06-02 alongside the model-rollback work folded into Phase 5. Key honesty point that motivated splitting this out: **model rollback ≠ full reproducibility** because lineage is corpus → model, not model → model. v1 ships the cheap flag (corpus hash); this seed is the real guarantee, deferred until rollback is in use and the flag proves insufficient.
