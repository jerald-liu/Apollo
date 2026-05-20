---
id: SEED-007
status: dormant
planted: 2026-05-20
planted_during: v2.0 / between Phase 03 (corpus-inference) and Phase 04 (evaluation loop)
trigger_when: Phase 4 is scoped; or user reports the model "feels boring" or "feels overfit"; or held-out scores stall across iterations
scope: Mixed — Tier 1+2 are Small (in scope for Phase 4 v1); Tier 3 is Large (v2 milestone)
---

# SEED-007: Internal metrics for training sufficiency & response diversity ("is it boring yet?")

## Why This Matters

Apollo's only signal today is **human rubric scores on held-out pairs**, computed once per iteration. That tells the user whether *this* checkpoint is better than the last, but it does not tell them *why* — is the model undertrained, overfit, fit-but-repetitive, or fit-but-corpus-too-thin? Each diagnosis has a different remedy:

| Diagnosis | Remedy |
|---|---|
| Undertrained | More epochs |
| Overfit | More regularization, more pairs |
| Fit but repetitive | Sampling controls (temperature/top-p), or model capacity |
| Fit but corpus too thin | More pairs, intentionally in under-represented modes/registers |
| Corpus too varied for the data | Either tighten corpus scope or accept higher loss floor |

Without internal metrics that distinguish these, the active-learning loop is opaque — the user is guessing at which lever to pull next.

A second, related problem: **"boring"** isn't a single failure mode. A model that emits the same response to every call is boring (low diversity). A model that emits wildly different responses, none of which fit, is also boring (low quality). The right metric distinguishes these.

## Three Tiers

### Tier 1 — Automatic internal metrics (in scope for Phase 4 v1)

Compute every iteration, log alongside train/val loss. Cheap, no human time.

- **Held-out val loss vs. train loss** — already in Phase 3's `train.py`. Add an explicit divergence detector ("val loss has been rising for K epochs while train loss falls").
- **Distinct-N over sampled responses.** For each held-out call, sample N (e.g. N=8) responses at fixed temperature; count unique n-grams (n=1..4) across the N samples. Higher = more diverse.
- **Self-BLEU.** For the same N samples, compute pairwise BLEU among them. Lower = more diverse. Self-BLEU and distinct-N complement each other.
- **Response entropy.** Mean per-token entropy of the model's output distribution at inference. Drops sharply when the model collapses to a few responses.
- **Calibration check.** Does increasing temperature actually increase distinct-N? If not, the model is over-confident and ignoring sampling controls — usually a sign of overfit.

These run on the existing held-out split. No new UI, no new corpus work.

### Tier 2 — Corpus-coverage gating (in scope for Phase 4 v1)

Same metrics, but interpreted as **prescriptions for the user**, not just diagnostics.

- **"Add more pairs" signal.** Val loss low + distinct-N low + self-BLEU high + entropy low = model has mastered a small corpus. Output: *"Your corpus has converged. The model is no longer learning. Author 10+ more pairs, ideally in under-represented modes/registers."*
- **Coverage map.** Cluster the held-out pairs by mel-encoder embedding and tokenized phrase shape. Surface which clusters have ≤2 examples — those are the under-represented regions of the user's style.
- **Train more vs. author more decision.** Tier 1 + Tier 2 together give an explicit recommendation each iteration: *"Train longer," "Author more," or "Tune sampling."*

Implementation: a `diagnose.py` script that reads the latest checkpoint and emits a structured report. Add to the per-iteration workflow.

### Tier 3 — Human pairwise ranking (v2 milestone)

When Tiers 1+2 say "model is fit and diverse but rubric scores still aren't improving," the bottleneck is **preference signal**, not capacity or data volume. This is where stack-ranking comes in.

- **Format:** For each held-out call, present N (e.g. N=4) candidate responses sampled at varying temperatures. User ranks them (or just picks best/worst). Optionally a Likert per candidate.
- **Use of signal — three increasingly ambitious uses:**
  1. **Inference-time reranking** (cheapest). At generation time, sample N candidates and score with a lightweight learned ranker over (call, response) pairs. User sees their preferences honored at inference without retraining.
  2. **Diagnostic feedback to corpus authoring.** Which authored pairs disagree most with the ranker's predictions? Those are the pairs that taught the model something contradictory — flag for the user to revisit or remove.
  3. **Reward modeling / RLHF-style fine-tuning** (most ambitious, requires real volume). Train a Bradley-Terry reward model on the rankings; fine-tune Apollo with PPO or DPO against it. Realistic only at ≥300 pairs and ≥1000 comparisons — not v1, not even early v2.

- **Cost:** UI to present candidates and capture rankings; storage schema for the rankings; annotation time. The annotation chore competes with authoring more pairs — that's the actual tradeoff, not the engineering.

## v1 / v2 Boundary

**v1 (Phase 4):** Ship Tier 1 + Tier 2. Both are pure computation on the existing held-out set; they require zero new UI and zero new annotation time. The "are you done training?" question gets a quantitative answer, and the "should you train more or author more?" question gets a prescription. This is high-leverage for low cost.

**v2 milestone (post-ship):** Tier 3. Defer until the corpus is large enough for the rankings to mean something (≥100 pairs, plausibly ≥300). The first useful application is inference-time reranking, *not* reward modeling — start there.

## Open Questions

1. **Distinct-N over what?** Raw token n-grams, or token-class n-grams (treating pitch as a class, velocity as a class)? Class-level is more musically meaningful but harder to interpret. Start with raw tokens; revisit if signal is noisy.
2. **What's a "good" distinct-N / self-BLEU value?** No universal answer — these are relative. Track deltas across iterations rather than absolute thresholds. The first iteration sets the baseline.
3. **Calibration check semantics.** "Does temperature actually move distinct-N?" implies running inference at multiple temperatures every diagnostic pass. Cost is N_temperatures × N_calls × N_samples forward passes — affordable on MPS for a 30-pair held-out set, may not be at 300 pairs. Subsample.
4. **Tier 3 rank vs. Likert vs. best-of-N.** Ranks give the most signal per click but are slowest. Best-of-N is fastest but lossy. The right format depends on annotation budget — design when Tier 3 surfaces, not now.
5. **Where does the coverage map live?** A static report per iteration? An interactive UI? CLI text? Tier 2's value drops sharply if the report is buried.

## How This Composes With Existing Seeds

- **SEED-004 (Bidirectional chaining):** When chains exist, Tier 1 metrics extend to "is the chain still diverse at turn 5?" — drift detection becomes a natural extension.
- **SEED-005 (Parameter locking):** Tier 2's coverage map highlights under-represented regions; SEED-005's UI is where the user would *act* on that by constraining future generations to fill the gap.
- **SEED-006 (Generative grammars):** Tier 3's rankings could be over (grammar-relation, response) pairs rather than raw responses — the ranker learns which *kinds* of responses fit which prompts, not just which tokens.

## When to Surface

**Trigger A:** Phase 4 (Evaluation Loop) is being scoped — Tier 1+2 should be in scope.
**Trigger B:** During the active-learning loop, the user reports the model "feels boring" or "feels overfit" — surface Tier 1 as a diagnostic.
**Trigger C:** Held-out rubric scores stall across two iterations despite continued authoring — surface Tier 2's coverage map and Tier 3 as next steps.

## Scope Estimate

**Tier 1+2 — Small.** Pure compute on existing held-out split. Maybe 1 plan in Phase 4: `diagnose.py` that loads a checkpoint, samples held-out responses at multiple temperatures, computes the metrics, and emits a structured report.

**Tier 3 — Large (v2 milestone).** New UI, new storage, new training loop branch (if reward modeling), new evaluation methodology. Realistic only once the corpus is large enough to make rankings statistically useful.

## Breadcrumbs

- `apollo/scripts/train.py` — already logs train/val loss per epoch; Tier 1's val/train divergence detector slots in here
- `apollo/scripts/generate.py` — Tier 1 reuses the sampling path; `diagnose.py` would call into it
- `apollo/model/mel_encoder.py` — embeddings for Tier 2's coverage clustering
- `.planning/REQUIREMENTS.md` — EVAL-01..EVAL-05; Tier 1+2 likely become one or two new EVAL-* requirements when Phase 4 is planned
- `.planning/ROADMAP.md` — Phase 4 (Evaluation Loop) is the home for Tier 1+2
- `.planning/seeds/SEED-002-hierarchical-call-and-response.md` — once theme-level pairs exist, diversity metrics extend to theme-level
- `.planning/seeds/SEED-004-bidirectional-chaining.md`, `SEED-005-parameter-locking-ui.md`, `SEED-006-generative-grammars-phrase-relations.md` — composition notes above

## Notes

The user's framing — *"if corpus depth is insufficient, prompt the user to stack-rank"* — gets the **escalation logic** exactly right: cheap automatic metrics first, human time only when automatic signal stalls. That ordering is what makes this tractable in a small-corpus active-learning regime. The trap to avoid is shipping Tier 3 before Tiers 1+2 — a stack-ranking UI without first diagnosing *why* the user is being asked to rank is just busywork.
