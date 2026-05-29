# Apollo Grading Rubric

The rubric is the source of truth for what "improvement" means in the active-learning
loop (EVAL-05). The grading UI shows shortened anchor strips inline; full anchor text
lives here. Do not edit the dimensions or anchor wording without re-scoring at least
one historical run — anchor drift invalidates cross-iteration deltas (D-02).

## How to grade

1. After a training run, render held-out responses:
   `python -m apollo.scripts.eval_render <checkpoint_path> [--iteration]`
   Then open Ableton and run the `m4l/ApolloRender.amxd` device against
   `eval/render_manifests/active.json` to bounce per-pair `response.wav`.
2. Start the grading UI:
   `python -m apollo.scripts.eval_grade data/pairs/ --run-id <run_id>`
3. For each held-out pair: hit Space, listen call → response, press `1`–`5` for fit,
   `Shift+1`–`Shift+5` for coherence, optionally `n` to note, `Enter` to submit.
4. Sessions are resumable — close the tab and re-launch; already-scored pairs show ✓.

## Dimensions

### Call-Response Fit (1–5) — THE SHIP-GATING DIMENSION (D-14)

- **1 — unrelated.** The response could have followed any call. No shared key, register,
  rhythm, or gestural logic.
- **2 — marginally related.** Some shared element (key, register, or rhythm) but no real
  call-and-response logic — the response is in the same neighbourhood, not in conversation.
- **3 — plausible.** Reasonable musical reply; nothing distinctive. A competent generic
  response, not specifically *yours*.
- **4 — strong.** Clearly answers the call; a choice you might make. The gesture's logic
  tracks back to something in the call.
- **5 — exactly what I'd play.** Indistinguishable from your own authoring intent. The
  response feels inevitable given the call.

### Musical Coherence (1–5) — TRACKED, NOT GATING (D-14)

- **1 — wrong notes.** Out-of-scale without purpose, untuned, or structurally broken.
- **2 — coherent but awkward.** Notes work but phrasing is off — timing, contour, or
  shape feels wrong as a standalone phrase.
- **3 — coherent statement.** Holds together as a phrase standalone, separable from the call.
- **4 — good phrase shape.** Intentional timing and contour; could appear in a sketch.
- **5 — could ship as-is.** Could appear in a finished piece without further editing.

## Free-text note (optional, D-03)

The note field captures qualitative signal for the next authoring round. Useful patterns:
- "tonic-bound" — model keeps landing on the root
- "rhythm matches but pitch random" — timing transfer works, pitch logic doesn't
- "second note feels late" — micro-timing miss
- "this is the gesture I always over-author" — corpus bias surfaced

Notes are scanned by hand when reviewing `eval/scores.jsonl` and when deciding what to
author next. They are not parsed or aggregated.

## Iteration marker (D-16, EVAL-05)

A run only counts toward the ship gate if it was rendered with `--iteration`. Sweeps,
debug runs, and ablations stay unmarked. The ship gate (`apollo eval ship-check`)
looks at the last two iteration-marked runs and checks that each beat its predecessor
in `runs.jsonl` on mean fit (D-14, D-16).

Mark only runs that represent a true corpus expansion / retraining round you want
measured. Over-marking dilutes the gate signal (RESEARCH Pitfall 8).

## Blind grading (D-05)

The UI hides run id / checkpoint / timestamp during scoring. A "🔎 reveal" link in the
pair footer surfaces them post-hoc. The blind default is a behavioural nudge, not a
security barrier — the user is both training target and grader; honour mode applies.
