# Phase 4: Evaluation Loop - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-21
**Phase:** 04-evaluation-loop
**Areas discussed:** Rubric design, Grading workflow / UX, Score persistence + delta surface, Ship-gate mechanics

---

## Rubric design

### Q: How many rubric dimensions per response (counting call-response-fit)?

| Option | Description | Selected |
|--------|-------------|----------|
| 2 dimensions | Call-response fit + one other (e.g. musical quality). Fastest to grade. | ✓ |
| 3 dimensions | Fit + rhythmic coherence + timbral appropriateness. | |
| 4–5 dimensions | Adds gesture completion, surprise/novelty. | |

**User's choice:** 2 dimensions (recommended)

### Q: How is the 1–5 scale anchored?

| Option | Description | Selected |
|--------|-------------|----------|
| Written anchors per point | 1='unrelated', 3='plausible response', 5='exactly what I'd play'. Reduces drift. | ✓ |
| Endpoints only | 1='bad', 5='great', middle is intuition. | |
| Free 1–5, no anchors | Pure gut. | |

**User's choice:** Written anchors per point (recommended)

### Q: If you add a second dimension beyond call-response fit, which?

| Option | Description | Selected |
|--------|-------------|----------|
| Musical coherence | Broad: does the response make musical sense as a phrase on its own? | ✓ |
| Rhythmic fit specifically | Does the response's rhythm complement the call's rhythm? | |
| Timbral appropriateness | Does the response choose notes that work for the call's preset? | |
| You decide | Claude's discretion. | |

**User's choice:** Musical coherence (recommended)

### Q: Should the rubric capture a free-text 'why' note per pair, or scores only?

| Option | Description | Selected |
|--------|-------------|----------|
| Optional free-text per pair | Scores + optional one-line note when something's notable. | ✓ |
| Scores only | Faster grading. | |
| Mandatory note on any score ≤2 | Forces articulation of failure. | |

**User's choice:** Optional free-text per pair (recommended)

---

## Grading workflow / UX

### Q: How does response.mid get rendered to audio for listening?

| Option | Description | Selected |
|--------|-------------|----------|
| Pre-render once per run, grade from .wav | Batch render upfront, fast grading after. | ✓ |
| Live Ableton import per pair | Manually drag each response.mid into Ableton. | |
| Headless render via external tool | Third-party OSC bridge or external FM renderer. | |

**User's choice:** Pre-render once per run, grade from .wav (recommended)

### Q: What does the grading session itself look like?

| Option | Description | Selected |
|--------|-------------|----------|
| Tiny local web UI | Browser page, click row → back-to-back playback, score sliders, note field. | ✓ |
| Terminal CLI prompt | afplay + stdin scores. | |
| Spreadsheet + manual playback | CSV + open .wav yourself. | |

**User's choice:** Tiny local web UI (recommended)

### Q: Blind or labeled grading?

| Option | Description | Selected |
|--------|-------------|----------|
| Blind by default, with reveal toggle | UI hides run/checkpoint while scoring. | ✓ |
| Always labeled | Always shows run/checkpoint. | |
| Always blind, no reveal | Strictest. | |

**User's choice:** Blind by default, with a reveal toggle (recommended)

### Q: How is a grading session structured?

| Option | Description | Selected |
|--------|-------------|----------|
| All held-out pairs, one sitting, resumable | ~5–10 min per run, resumable. | ✓ |
| Batched (e.g. 10 at a time) | Forces breaks. | |
| You decide | Planner picks. | |

**User's choice:** All held-out pairs, one sitting, resumable (recommended)

### Q (follow-up): How is the per-run pre-render actually executed?

| Option | Description | Selected |
|--------|-------------|----------|
| Manual Ableton session per run | Prepared 'eval' Ableton set, manual import-and-bounce pass. | |
| Max-for-Live render device | M4L device watches folder, auto-bounces incoming .mid. | ✓ |
| Defer | Lock upstream decisions, treat render as sub-decision. | |

**User's choice:** Max-for-Live render device

**Notes:** User then clarified the M4L device should be designed with both corpus-authoring and evaluation in mind — "1 per phrase (call track + response track)", proposed name "Corpus Training". This expanded into three follow-up questions below.

### Q (clarifier): Does the M4L device subsume the web UI, or do both exist?

| Option | Description | Selected |
|--------|-------------|----------|
| M4L device is the only grader | All grading inside Ableton. | |
| Both — M4L for in-session, web UI as fallback | Two scoring surfaces. | |
| Web UI primary, M4L only for rendering | M4L produces response.wav, grading in browser. | ✓ |

**User's choice:** Web UI primary, M4L only for rendering

### Q (clarifier): Where does the Corpus Training device get built — Phase 3 or Phase 4?

| Option | Description | Selected |
|--------|-------------|----------|
| Phase 3 authoring mode, Phase 4 eval mode | Shared artifact, scoped per phase. | |
| Whole device in Phase 3 | Both modes shipped at once. | |
| Whole device in Phase 4; Phase 3 stopgap | Python folder-watcher + manual bounce in Phase 3. | ✓ |

**User's choice:** Build the whole device in Phase 4; Phase 3 uses a stopgap export workflow

### Q (clarifier): Does the device need to coordinate across both tracks?

| Option | Description | Selected |
|--------|-------------|----------|
| Independent, share via folder convention | Devices communicate only via data/pairs/NNN/. | ✓ |
| Coordinated via M4L globals / Live API | Devices know about each other. | |
| Single device on a master/utility track | One device references both tracks. | |

**User's choice:** Independent, share via folder convention (recommended)

---

## Score persistence + delta surface

### Q: Storage format for scores?

| Option | Description | Selected |
|--------|-------------|----------|
| JSONL, one record per (run, pair, dim) | Append-only, git-diffable. | ✓ |
| SQLite | Better querying as runs accumulate. | |
| Wide CSV | Visually scannable. | |

**User's choice:** JSONL, one record per (run, pair, dim) (recommended)

### Q: How is a 'run' identified?

| Option | Description | Selected |
|--------|-------------|----------|
| Auto-derived: checkpoint hash + corpus hash + timestamp | No manual tagging, reproducible. | ✓ |
| Manual tag (e.g. 'iter-3') | User types name. | |
| Checkpoint filename only | Fragile. | |

**User's choice:** Auto-derived: checkpoint hash + corpus hash + timestamp (recommended)

### Q: What metadata travels with each run?

| Option | Description | Selected |
|--------|-------------|----------|
| Checkpoint hash, corpus pair-ID list, training config, date | Full diagnostic context. | |
| Just checkpoint hash + date | Minimal. | |
| You decide | Planner picks. | ✓ |

**User's choice:** You decide (Claude's discretion)

### Q: What does 'show me the delta' look like?

| Option | Description | Selected |
|--------|-------------|----------|
| Terminal table + markdown report file | `apollo eval report` + persistent .md history. | |
| Terminal table only | Lightest. | |
| Notebook / matplotlib plot | Trend visualization, exploratory. | ✓ |

**User's choice:** Notebook / matplotlib plot

---

## Ship-gate mechanics

### Q: What counts as 'improvement' between runs?

| Option | Description | Selected |
|--------|-------------|----------|
| Mean call-response-fit up by any ε | Strict literal EVAL-05. | ✓ |
| Both dimensions up | Both fit AND musical coherence. | |
| Threshold (e.g. +0.1 on 1–5 scale) | Filters noise. | |

**User's choice:** Mean call-response-fit up by any ε (recommended)

### Q: Per-pair regression tolerance — can individual pairs get worse?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — mean is what counts | Per-pair regressions for diagnostics only. | ✓ |
| No catastrophic drops: cap at -2 per pair | Catches asymmetric improvements. | |
| No regressions at all | Every pair must be ≥ prior run. | |

**User's choice:** Yes — mean is what counts (recommended)

### Q: Which two runs count as the 'two consecutive' for the ship gate?

| Option | Description | Selected |
|--------|-------------|----------|
| Any two adjacent runs in time order | Most recent and predecessor. | |
| Explicit 'iteration' marker per run | User tags runs that count as iteration boundaries. | ✓ |
| Same corpus pair-set, different checkpoints | Already true by construction. | |

**User's choice:** Explicit 'iteration' marker per run

### Q: How does the gate get announced?

| Option | Description | Selected |
|--------|-------------|----------|
| `apollo eval ship-check` exit code + report banner | CLI subcommand, 0 if gate met. | ✓ |
| Automatic git tag on pass | Tag checkpoint when gate trips. | |
| Manual review only — just a report | No dedicated command. | |

**User's choice:** `apollo eval ship-check` exit code + report banner (recommended)

---

## Claude's Discretion

- Run-level metadata fields in `runs.jsonl` (Q: "What metadata travels with each run?")

## Deferred Ideas

- Corpus Training device authoring-mode (M4L device that exports `call.mid`/`call.wav`/`response.mid` from Ableton). Scoped out of Phase 4; Phase 3 uses a stopgap.
- In-session grading inside the M4L device itself. Rejected for v1; web UI is the grader.
- `apollo eval report` markdown report writer. Notebook covers it for v1.
- Per-dim ship-gating, regression caps, ε floors for "meaningful" improvement. All rejected — strict literal EVAL-05 wins for v1.
- Auto-tagging checkpoints on gate pass.
