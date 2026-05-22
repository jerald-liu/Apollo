# Phase 4: Evaluation Loop — Research

**Researched:** 2026-05-21
**Domain:** Local web UI (grading), JSONL score persistence, run-identity hashing, Jupyter delta notebook, Max-for-Live MIDI→audio bounce device, CLI ship-gate
**Confidence:** HIGH for Python/web/JSONL/Notebook/CLI tooling. MEDIUM for the Max-for-Live device — Live's render-to-disk API is not officially documented for batched programmatic export; the recommended approach is pragmatic and load-bearing on user testing.

## Summary

Phase 4 builds five mostly-independent tools that share one filesystem contract (`eval/` and `data/pairs/NNN/eval/{run_id}/`):

1. A **tiny Flask app** (~5 routes, ~150 LOC) that lists held-out pairs, serves their `call.wav` + `response.wav`, accepts two integer scores + an optional note, and appends one JSONL line per (run, pair, dim).
2. A **JSONL score store** at `eval/scores.jsonl` and a **run manifest** at `eval/runs.jsonl` — both append-only, written one line at a time with `open(..., "a")` + `f.write(json.dumps(...) + "\n")` + `f.flush()` (atomic per-line on POSIX local FS for lines under PIPE_BUF / 4 KB). Resumability is "read scores.jsonl filtered to current run_id and skip those pairs."
3. A **run identity hash**: `blake2b(checkpoint_bytes + sorted_pair_ids_joined, digest_size=8).hexdigest()` → 16-char hex. Stable across runs/platforms, short enough to type, paired with an ISO timestamp for human readability.
4. A **Max-for-Live device** that walks a list of `response.mid` file paths fed from a JSON manifest, loads each into a clip slot via the Live Object Model (LOM), plays the clip, and uses Live's offline render (`Set.export_audio` is NOT a public API — the safe path is `[sfrecord~]` capturing the device chain's audio output during real-time playback). Identified landmines: Live's transport state, freeze-on-export quirks, and the fact that there is no officially-supported "headless render N clips to N files" API in Live 12.
5. A **Jupyter notebook** at `eval/delta.ipynb` reading both JSONL files into pandas, with two plot families (per-dim mean over runs, per-pair score trajectories) plus a small ship-gate explainer cell.
6. A **CLI subcommand `apollo eval ship-check`** implemented as `apollo/scripts/eval_ship_check.py` (since the project has no `apollo` console-script entry yet — every existing tool is invoked as `python -m apollo.scripts.<name>`). Pure function over `runs.jsonl` + `scores.jsonl`; trivially CI-testable.

**Primary recommendation:** Flask + plain HTML + vanilla JS; `blake2b` for the run hash; one JSONL append per submit with a per-record `(run_id, pair_id, dim)` natural key; `pandas` + `matplotlib` for the notebook; M4L device built around `[sfrecord~]` + JS `LiveAPI` for clip loading; CLI subcommand as a standalone module mirroring the existing `train.py` / `generate.py` pattern.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Rubric (EVAL-01)**
- D-01: Two scoring dimensions: **call-response fit (1–5)** and **musical coherence (1–5)**. Two is the deliberate ceiling — 30 held-out pairs × 2 dims = ~5–10 min/session.
- D-02: Both scales have written anchors per scale point (e.g. 1 = "unrelated", 3 = "plausible", 5 = "exactly what I'd play"). Non-negotiable for cross-iteration signal validity.
- D-03: Each pair carries an **optional free-text note**. Optional, not mandatory.

**Grading workflow / UX (EVAL-02)**
- D-04: Grader is a **tiny local web UI** (Flask/FastAPI + plain HTML). Worklist of held-out pairs → click row → play call.wav then response.wav → sliders/keys for scores + note → submit writes incrementally. Sessions resumable.
- D-05: **Blind by default with reveal toggle**. UI hides run/checkpoint metadata while scoring; toggle reveals post-hoc.
- D-06: All held-out pairs, one sitting, resumable. Not enforced batching.
- D-07: Response audio **pre-rendered once per run** via the M4L device. Grader plays static `.wav`s; no Ableton interaction during scoring.

**Score persistence + delta (EVAL-03, EVAL-04)**
- D-08: Score store = **JSONL, one record per (run, pair, dimension)** at `eval/scores.jsonl`. Append-only, git-diffable, no schema migrations. Separate `eval/runs.jsonl` for run-level metadata. Exact run-level fields = Claude's discretion.
- D-09: **Run identity auto-derived** — short hash of (checkpoint file bytes + sorted training pair-IDs) + ISO timestamp. No manual tagging.
- D-10: Delta surface = **Jupyter notebook** at `eval/delta.ipynb` with matplotlib. Per-dim mean across runs over time + per-pair trajectories.

**Audio rendering — M4L device**
- D-11: M4L device on response track, loads `response.mid`, plays through loaded Operator, bounces to `data/pairs/NNN/eval/{run_id}/response.wav`.
- D-12: Rendering-only in Phase 4; no grading, no corpus authoring.
- D-13: Call-track and response-track instances are **independent**, coordinate via folder convention. No M4L inter-device messaging.

**Ship-gate (EVAL-05)**
- D-14: Improvement = mean call-response-fit up by any ε between designated runs. Musical coherence tracked but **not gating**.
- D-15: No per-pair regression tolerance. Per-pair regressions are notebook-visible only.
- D-16: Consecutive iteration-marked runs identified via explicit `iteration: true` flag on the run record. Sweeps/debug runs don't count.
- D-17: Ship-gate via **`apollo eval ship-check`** CLI → exit 0 if gate met, non-zero otherwise. Prints two deltas. No auto-tag, no auto-ship.

### Claude's Discretion
- Exact run-level metadata fields in `runs.jsonl` (at minimum: checkpoint hash, corpus pair-ID list, training config snapshot, timestamp, iteration marker; may add git SHA, total steps).
- File layout details under `eval/`.
- Web UI tech stack within "local web UI" (Flask vs FastAPI vs http.server + static — cheapest-to-build).
- M4L device internal architecture and held-out walkthrough parameterization.
- Notebook structure beyond the two required plot families.

### Deferred Ideas (OUT OF SCOPE)
- Corpus Training device (authoring-mode M4L). Phase-3 stopgap covers authoring.
- In-session grading inside Ableton (M4L-native scoring UI). Web UI handles grading.
- `apollo eval report` markdown writer. Notebook + ship-check are sufficient.
- Per-dim ship-gating, regression caps, ε floors.
- Auto-tagging checkpoints when the gate passes.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| EVAL-01 | Listen-test rubric with "call-response fit" (1–5) + ≥1 other musical-quality dim, documented | §"Rubric Schema" — two-dim rubric + anchors + free-text note (D-01..D-03) |
| EVAL-02 | Grading workflow plays call → response back-to-back per held-out pair | §"Web UI", §"Blind Grading UX" — Flask app + HTML5 audio sequencing + reveal toggle |
| EVAL-03 | Held-out scores persisted per run (CSV/JSON) so deltas across iterations are visible | §"JSONL Schema + Append Safety" — `eval/scores.jsonl` + `eval/runs.jsonl` |
| EVAL-04 | Tracking surface (script or doc) showing score-per-iteration deltas across runs | §"Delta Notebook Structure" — `eval/delta.ipynb` with two required plot families |
| EVAL-05 | v1 ships only when two consecutive iteration rounds both improve mean held-out call-response-fit | §"Ship-Gate CLI" — `eval_ship_check.py` pure-function over runs.jsonl + scores.jsonl |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Local-only training on Apple Silicon (MPS).** No Modal/cloud. Phase 4 is even more local — the web UI binds to `127.0.0.1` and the M4L device runs inside Live on the user's machine.
- **Train from scratch, response-only loss.** No bearing on Phase 4 directly — eval consumes the artifacts produced by Phase 3.
- **Monophonic + tiny gestures, 0.5–1.5 sec.** Bearing on M4L: each held-out clip is ≤ 1.5 s of MIDI; bounce length is bounded, so per-pair render time is small (clip length + small Operator release-tail buffer).
- **The active-learning loop is the product.** Phase 4 IS the loop. Every design choice here optimizes for "user actually sits down and grades 30 pairs in 10 min, then can immediately see the delta."
- **`response_NNN.mid` (Phase 3 INFER-01) is the input to the M4L renderer.** generate.py writes these alongside `call.mid` in each pair dir (D-17 of 03-CONTEXT.md). Phase 4 must pick *one* `response.mid` per held-out pair per run; recommendation = `response_001.mid` (the first/single generation), with planner free to revisit if N-sample auditioning becomes a graded feature later.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Hold-out enumeration | Python (`apollo/eval/heldout.py`) | reuses `apollo.ingest.split.is_heldout` + `discover_pairs` | Single source of truth for which pairs are eval-eligible |
| Run identity hashing | Python (`apollo/eval/run_id.py`) | hashlib (stdlib) | Pure function, fully unit-testable, no I/O beyond reading the checkpoint file |
| Run manifest write | Python (`apollo/eval/runs_log.py`) | json + open(..., "a") | One JSON-line per run, appended once per `apollo eval render` invocation |
| Per-pair render orchestration | M4L device + Python helper (`apollo/eval/render_manifest.py`) | Live Object Model, JS in `[js]` object | Live owns audio I/O; Python prepares the manifest of (response.mid path → output.wav path) |
| Audio bounce | M4L device (`[sfrecord~]` chain) | Live's clip transport | Render-to-disk happens inside Live; nothing else in stack has access to Operator's audio output |
| Web UI server | Python (`apollo/eval/web/app.py`) | Flask | Local-only, ~5 routes, blueprint optional |
| Score JSONL append | Python (`apollo/eval/scores_log.py`) | json + open(..., "a") + flush | Append-only contract enforced behind a single function |
| Delta visualization | Jupyter (`eval/delta.ipynb`) | pandas + matplotlib | User asked for exploratory notebook explicitly (D-10) |
| Ship-gate decision | Python (`apollo/scripts/eval_ship_check.py`) | reads runs.jsonl + scores.jsonl | Pure logic, CI-testable; exit code = answer |

## Standard Stack

### Core (already in pyproject.toml)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib (`json`, `hashlib`, `pathlib`, `argparse`, `csv`) | 3.11+ | JSONL I/O, hashing, CLI | Project is already Python-stdlib-first; no reason to deviate |
| pretty_midi | 0.2.11 | (not used in Phase 4 directly, but the M4L manifest references `response.mid` produced by Phase 3 which uses it) | Existing project convention |

### Net-new dependencies (add to `[project.optional-dependencies]` under a new `eval` extra)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| **Flask** | 3.0+ | Local web UI (≤5 routes) | Smallest mainstream web framework; zero config; `flask --app apollo.eval.web run` is one line. [VERIFIED via pip registry: Flask 3.0.3 current stable as of 2024-09. Stable API.] |
| **pandas** | 2.x | Notebook DataFrame ops over JSONL | Standard; reads `pd.read_json("scores.jsonl", lines=True)` directly. |
| **matplotlib** | 3.x | Notebook plots | Standard; D-10 specifies matplotlib. |
| **jupyter** | (jupyterlab or notebook) | Notebook host | User-facing tool; install once. |

**Installation:**
```
pip install -e ".[eval]"
```
where pyproject.toml grows:
```
[project.optional-dependencies]
eval = ["flask>=3.0", "pandas>=2.0", "matplotlib>=3.7", "jupyter>=1.0"]
```

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Flask | FastAPI | FastAPI adds async (we don't need it), pydantic (we don't need it), uvicorn (extra process surface). For 5 routes serving local files, Flask wins on cheapness. |
| Flask | `http.server` + static HTML (no framework) | Static HTML can't accept POST scores cleanly without writing a request handler subclass — at which point you've built half of Flask. Flask is the floor. |
| blake2b | sha256 truncated | Both work. blake2b lets us specify `digest_size=8` directly; sha256 needs `[:16]` slicing. blake2b is also slightly faster on small inputs. Either is fine; recommend blake2b for the API ergonomics. |
| pandas in notebook | Pure stdlib (`json.loads` + lists) | Pandas makes "filter to run X, group by dim, mean over pair" a one-liner. Worth the dependency in a notebook. |

**Version verification:** Run `pip show flask pandas matplotlib jupyter` after install to confirm. As of 2026-05, all are mature with stable APIs.

## Architecture Patterns

### System Architecture Diagram

```
User authors pairs in Ableton (Phase 3)
                  │
                  ▼
        data/pairs/NNN/{call.mid, call.wav, response.mid}
                  │
                  ▼
        apollo/scripts/train.py  → models/run-{iter:02d}-{ts}.pt   [Phase 3]
                  │
                  ▼
        apollo/scripts/generate.py (each held-out pair)
                  │
                  ▼
        data/pairs/NNN/response_001.mid  [Phase 3 output, Phase 4 input]
                  │
                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ PHASE 4 STARTS HERE                                                       │
│                                                                           │
│ apollo eval render <checkpoint_path>                                      │
│   ├─ compute run_id = blake2b(checkpoint_bytes + sorted_train_ids)        │
│   ├─ enumerate held-out pairs (is_heldout(nnn))                          │
│   ├─ write eval/runs.jsonl line {run_id, checkpoint_hash, iteration, ...}│
│   └─ write eval/render_manifests/{run_id}.json:                          │
│      [{response_mid: "data/pairs/007/response_001.mid",                  │
│        out_wav:     "data/pairs/007/eval/{run_id}/response.wav"}, ...]   │
│                          │                                                │
│                          ▼                                                │
│   USER opens Ableton, loads M4L device on response track,                │
│   points it at the manifest. Device walks the list:                      │
│      load clip → play → [sfrecord~] captures audio → write .wav          │
│                          │                                                │
│                          ▼                                                │
│   data/pairs/NNN/eval/{run_id}/response.wav exists for every held-out NNN│
│                          │                                                │
│                          ▼                                                │
│ apollo eval grade                                                         │
│   ├─ starts Flask at http://127.0.0.1:5000                               │
│   ├─ GET /  → list of held-out pairs, status (graded / pending)         │
│   ├─ GET /pair/<nnn> → player + sliders + note field                    │
│   ├─ GET /audio/<nnn>/call.wav  → serves data/pairs/NNN/call.wav        │
│   ├─ GET /audio/<nnn>/response.wav → serves the per-run rendered wav    │
│   └─ POST /score  → appends 2 lines to eval/scores.jsonl                │
│                       (one per dim, both written atomically per submit)  │
│                          │                                                │
│                          ▼                                                │
│ eval/scores.jsonl grows; resumability = read it, skip graded pairs       │
│                          │                                                │
│                          ▼                                                │
│ eval/delta.ipynb  ← user opens, hits Run All                              │
│   ├─ load runs.jsonl + scores.jsonl with pd.read_json(... lines=True)    │
│   ├─ plot per-dim mean over runs                                         │
│   └─ plot per-pair score trajectories                                    │
│                          │                                                │
│                          ▼                                                │
│ apollo eval ship-check                                                    │
│   ├─ find last two iteration-marked runs + their predecessors            │
│   ├─ compute mean call-response-fit delta for each pair                  │
│   └─ exit 0 if both deltas > 0, else exit non-zero; print banner         │
└──────────────────────────────────────────────────────────────────────────┘
```

### Recommended Project Structure

```
apollo/
├── eval/                            # NEW package
│   ├── __init__.py
│   ├── heldout.py                   # enumerate_heldout(pairs_root) -> List[PairPath]
│   ├── run_id.py                    # compute_run_id(ckpt_path, train_pair_ids) -> str
│   ├── runs_log.py                  # append_run(record, path="eval/runs.jsonl")
│   ├── scores_log.py                # append_score(run_id, pair_id, dim, score, note)
│   │                                # load_scores(run_id=None) -> List[dict]
│   ├── ship_check.py                # check_ship_gate(runs_jsonl, scores_jsonl) -> (passed, msg)
│   ├── render_manifest.py           # write_manifest(run_id, heldout_pairs) -> path
│   └── web/
│       ├── __init__.py
│       ├── app.py                   # create_app() factory; 5 routes
│       ├── templates/
│       │   ├── index.html           # worklist
│       │   └── pair.html            # player + scoring form
│       └── static/
│           ├── grade.js             # audio sequencing + form submit
│           └── style.css            # minimal styling
├── scripts/
│   ├── eval_render.py               # `python -m apollo.scripts.eval_render <ckpt>`
│   ├── eval_grade.py                # `python -m apollo.scripts.eval_grade`
│   └── eval_ship_check.py           # `python -m apollo.scripts.eval_ship_check`
│
eval/                                # NEW top-level dir (gitignored except .ipynb + rubric.md)
├── rubric.md                        # written anchors per scale point (D-02) — committed
├── delta.ipynb                      # committed
├── scores.jsonl                     # gitignored (regenerable from sessions)
├── runs.jsonl                       # gitignored (regenerable from training history)
└── render_manifests/                # gitignored
    └── {run_id}.json

m4l/                                 # NEW top-level dir
└── ApolloRender.amxd                # binary M4L device — committed (small)
└── ApolloRender.README.md           # device contract + setup instructions

tests/
├── test_run_id.py                   # hash determinism + checkpoint-path -> hash
├── test_ship_check.py               # gate logic: trips/doesn't-trip cases
├── test_scoring.py                  # JSONL append + load + duplicate detection
├── test_render_manifest.py          # manifest write + heldout enumeration
└── test_eval_web.py                 # Flask test client smoke (GET /pairs, POST /score)
```

**Why this layout:**
- `apollo/eval/` mirrors `apollo/ingest/` and `apollo/model/` — same idiom the project already uses.
- `eval/` top-level (vs. nested under apollo) keeps notebook + rubric + JSONL data files at the repo root where the user actually opens them. Matches `models/`, `data/`, `logs/` precedent.
- `m4l/` is separate from Python code: the device is a binary artifact, the README documents its contract.

### Pattern 1: Append-only JSONL with per-line atomicity

**What:** Open file with mode `"a"`, write `json.dumps(record, separators=(",", ":")) + "\n"`, then `f.flush()` and optionally `os.fsync(f.fileno())`. Each `write()` of a line under ~4 KB is atomic on POSIX local filesystems (the page cache write is the whole line or nothing, given `O_APPEND` semantics).

**When to use:** Phase 4 score submits + run records — every append.

**Example:**
```python
# Source: apollo/eval/scores_log.py — pattern recommended for Phase 4
import json
from pathlib import Path
from datetime import datetime, timezone

def append_score(run_id: str, pair_id: str, dim: str, score: int,
                 note: str = "", path: str = "eval/scores.jsonl") -> None:
    """Append one (run_id, pair_id, dim) score record. Atomic per line on POSIX local FS."""
    assert dim in {"fit", "coherence"}, f"unknown dim {dim!r}"
    assert 1 <= score <= 5, f"score {score} outside 1..5"
    record = {
        "run_id": run_id,
        "pair_id": pair_id,
        "dim": dim,
        "score": score,
        "note": note,
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, separators=(",", ":")) + "\n")
        f.flush()  # ensures crash-after-submit doesn't lose the line
```

**De-dup contract:** Submitting a new score for the same (run_id, pair_id, dim) appends another line. The notebook + ship-check **always take the *last* line per key** (idiomatic JSONL "latest write wins"). Document this in a docstring; do NOT try to mutate / rewrite the file.

[CITED: standard JSONL convention used by HuggingFace datasets, OpenAI fine-tuning, etc. No external doc needed for the idiom but the per-line atomicity guarantee on POSIX is well-known stdlib behavior.]

### Pattern 2: Run-identity hash

**What:** `blake2b(checkpoint_bytes_concat_with_pair_id_list, digest_size=8).hexdigest()` → 16 hex chars.

**Why blake2b:** Built into stdlib (`hashlib.blake2b`); supports configurable `digest_size` directly (no slicing); faster than sha256 on small inputs; cryptographically strong (we don't need crypto strength but there's no reason to use a weaker hash).

**Why include both checkpoint bytes AND sorted pair-IDs:** A checkpoint trained on corpus v1 vs v2 may have identical weights by chance (extremely unlikely but) and certainly identical-bit checkpoints exist if re-trained from same seed on same corpus. The pair-ID list tags the *corpus* that was the training input; combined they uniquely identify the (model, data) tuple, which is the actual identity that matters for the active-learning loop.

**Example:**
```python
# Source: apollo/eval/run_id.py
import hashlib
from pathlib import Path
from typing import Iterable

def compute_run_id(checkpoint_path: str, train_pair_ids: Iterable[str]) -> str:
    """Stable 16-char hash of (checkpoint bytes, sorted training pair-IDs).

    Reads the checkpoint in chunks to avoid loading multi-MB into memory.
    Same (ckpt file, corpus) → same run_id, deterministic across platforms.
    """
    h = hashlib.blake2b(digest_size=8)
    p = Path(checkpoint_path)
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            h.update(chunk)
    # delimiter byte prevents pair-ID collision with checkpoint suffix
    h.update(b"\x00CORPUS\x00")
    for pid in sorted(train_pair_ids):
        h.update(pid.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()  # 16 hex chars
```

[CITED: https://docs.python.org/3/library/hashlib.html#blake2 — `digest_size` parameter documented since 3.6.]

**Human-readable timestamp:** Stored as a *separate* field in `runs.jsonl`, e.g. `"created": "2026-05-21T14:32:18Z"`. The run_id is for machine identity (joins across JSONL files); the timestamp is for human reading.

### Pattern 3: Flask local-only minimal app

**What:** A factory function returning a `Flask` app, served via `flask --app apollo.eval.web run --host 127.0.0.1 --port 5000`. Five routes, no auth (local-only), no database — JSONL is the data layer.

**Example skeleton:**
```python
# Source: apollo/eval/web/app.py — recommended for Phase 4

from flask import Flask, render_template, request, send_file, abort, jsonify, redirect, url_for
from pathlib import Path
from apollo.eval.scores_log import append_score, load_scores
from apollo.eval.heldout import enumerate_heldout

def create_app(pairs_root: str, run_id: str, eval_root: str = "eval") -> Flask:
    app = Flask(__name__)
    app.config["PAIRS_ROOT"] = Path(pairs_root)
    app.config["RUN_ID"] = run_id
    app.config["EVAL_ROOT"] = Path(eval_root)

    @app.get("/")
    def index():
        held = enumerate_heldout(app.config["PAIRS_ROOT"])
        scored = load_scores(run_id=run_id)  # dict[(pair_id, dim)] -> latest record
        graded_pairs = {k[0] for k in scored if scored[k]["dim"] in ("fit","coherence")}
        # ... build worklist with status badges
        return render_template("index.html", pairs=held, graded=graded_pairs, blind=True)

    @app.get("/pair/<nnn>")
    def pair_view(nnn):
        # render player + sliders. Pass blind=True; template hides run_id metadata.
        return render_template("pair.html", nnn=nnn, run_id_visible=False)

    @app.get("/audio/<nnn>/call.wav")
    def call_audio(nnn):
        path = app.config["PAIRS_ROOT"] / nnn / "call.wav"
        if not path.is_file(): abort(404)
        return send_file(path, mimetype="audio/wav")

    @app.get("/audio/<nnn>/response.wav")
    def response_audio(nnn):
        path = app.config["PAIRS_ROOT"] / nnn / "eval" / run_id / "response.wav"
        if not path.is_file(): abort(404)
        return send_file(path, mimetype="audio/wav")

    @app.post("/score")
    def submit_score():
        data = request.get_json()
        # data = {"pair_id": "007", "fit": 4, "coherence": 3, "note": "tonic-bound"}
        append_score(run_id, data["pair_id"], "fit", data["fit"], data.get("note",""))
        append_score(run_id, data["pair_id"], "coherence", data["coherence"], "")
        return jsonify({"ok": True})

    @app.get("/reveal/<nnn>")  # D-05 reveal toggle
    def reveal(nnn):
        return jsonify({"run_id": run_id, "ckpt": "<read from runs.jsonl>"})

    return app
```

**Run command:**
```
python -m apollo.scripts.eval_grade data/pairs/ --run-id <run_id>
```
which in turn calls `create_app(...)` then `app.run(host="127.0.0.1", port=5000)`.

[CITED: https://flask.palletsprojects.com/en/3.0.x/quickstart/ — application factory pattern.]

### Pattern 4: Max-for-Live audio bounce via `[sfrecord~]`

**What:** The device sits on the response track that already hosts an Operator instrument. Internally it has:
- A `[js]` object running a script that uses the **Live Object Model (LOM)** via `LiveAPI` to walk a manifest and load `response.mid` files into the track's first clip slot one at a time (`track.clip_slots[0].set("file_path", ...)` — note: **clip import from a file path is supported in Live 12 via the LOM** but is the trickiest part; see Pitfall §below).
- An `[sfrecord~]` object connected to the device's audio inlets (which receive the *output of the entire track's instrument chain*, i.e. Operator's audio).
- A small state machine: `open <out_wav>` → `record 1` → `play_clip()` → wait until clip end → `record 0` → `close` → advance manifest.

**Why this approach (vs. Live's "Export Audio/Video" menu):** Live's "Export Audio/Video" is a UI command, not exposed in the LOM. There is no `Set.export_audio(...)` Python API. Programmatic batch export is not a first-class Live feature in Live 12 (verified across Live 11/12 LOM docs); `[sfrecord~]` is the standard workaround. It captures real-time audio from a signal flow inside Max — perfectly clean if the device is the last item in the chain.

**Key API references (M4L / Live 12 LOM):**
- `live.thisdevice` — fires `bang` when the device + Live set are fully loaded; gate the start of the manifest walk on this.
- `live.path` / `live.object` / `LiveAPI` from JS — navigate `live_set tracks N clip_slots 0` and call `create_clip` or set `file_path` on the clip slot.
- `[sfrecord~] <samplerate> <bit_depth> wave` — opens a wav at a path, records until stopped.

[CITED: Live Object Model reference — `LiveAPI` JS docs in Max 8/9, Cycling '74 documentation. Live 12 LOM is backward-compatible with Live 11.]

**Pitfalls — surface during planning:**
1. **Loading a `.mid` from disk into a clip slot programmatically is poorly documented.** Two approaches: (a) drag-and-drop simulation via `LiveAPI` `create_clip` + manually inserting notes parsed from the MIDI file (more reliable but requires parsing MIDI in JS, which is painful), or (b) using `LiveAPI` to set the `file_path` attribute of an empty clip slot — works in some Live versions but is brittle. **Recommendation:** Approach (a). The M4L device's JS reads the MIDI via a small JS MIDI parser (or simpler: the Python preprocessor writes a JSON `.json` file alongside each `response.mid` with `[{pitch, velocity, start_beats, end_beats}, ...]`, and the JS reads JSON and creates clip notes directly via `add_new_notes`). The JSON sidecar simplifies the JS dramatically.
2. **Transport state.** `[sfrecord~]` records based on signal flow, not transport. Starting the recorder, then triggering clip playback, then stopping the recorder after clip length + small tail (200 ms for Operator's release envelope) gives clean audio.
3. **Freeze vs render.** Track freeze creates a track-wide audio bounce but mixes in all effects and is not file-path-controllable. Don't use freeze; use `[sfrecord~]`.
4. **Sample rate / bit depth.** Set `[sfrecord~]` to match Live's current sample rate (`live.thisdevice` reports it). 24-bit float wav is fine; for grading audio quality is over-determined — even 16-bit PCM is enough. **Recommendation:** 44100 Hz / 16-bit, mono. Matches what grading needs and keeps wav file size small.
5. **Stereo vs mono.** Operator outputs stereo. Recommendation: bounce stereo (matches what the user hears in Ableton). Web UI's `<audio>` element handles either.
6. **Recording silence after clip end.** Use a `[timer]` set to clip duration + 200 ms; on timer fire, stop recording. Don't rely on clip-end LOM notifications — they fire too late.
7. **Run failure recovery.** If the manifest walk crashes mid-way, partial wavs exist. The web UI's `/audio/<nnn>/response.wav` route returns 404 for missing files; the worklist should mark those pairs as "unrenderable" with a re-render button (or just: user re-runs the device).

**Minimum viable device file structure (described, not coded — implementation is a planner concern):**
- One `.amxd` device, ~6 objects: `[live.thisdevice]`, `[js render_walker.js]`, `[sfrecord~ 44100 16 mono]` (or stereo), a `[live.text]` "Start" button, a `[live.numbox]` showing current pair index, and a `[print]` for debugging.
- Configuration: device reads the manifest path from a `[live.path]` attribute or a hardcoded relative path `../../eval/render_manifests/active.json` (planner picks). User points the device at the run by changing the path or having `apollo eval render` write to a known location.

### Pattern 5: Pure-function ship-gate

**What:** Read both JSONL files; reduce scores to "latest score per (run, pair, dim)"; identify last two iteration-marked runs + their predecessors; compute mean fit-delta per pair.

**Example:**
```python
# Source: apollo/eval/ship_check.py — recommended for Phase 4

from typing import List, Tuple
import json
from pathlib import Path
from collections import defaultdict

def _load_jsonl(path: str) -> List[dict]:
    if not Path(path).is_file():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]

def _latest_scores_per_run(scores: List[dict]) -> dict:
    """{(run_id, pair_id, dim): latest_score} — JSONL last-write-wins."""
    out = {}
    for rec in scores:  # insertion order = file order = chronological
        out[(rec["run_id"], rec["pair_id"], rec["dim"])] = rec["score"]
    return out

def _mean_fit(run_id: str, latest: dict) -> float:
    fits = [v for (rid, _, dim), v in latest.items() if rid == run_id and dim == "fit"]
    if not fits:
        return float("nan")
    return sum(fits) / len(fits)

def check_ship_gate(runs_path: str = "eval/runs.jsonl",
                    scores_path: str = "eval/scores.jsonl") -> Tuple[bool, str]:
    runs = _load_jsonl(runs_path)
    scores = _load_jsonl(scores_path)
    latest = _latest_scores_per_run(scores)

    # All runs, in chronological order (file order)
    iter_runs = [r for r in runs if r.get("iteration") is True]

    if len(iter_runs) < 2:
        return False, f"Need ≥2 iteration-marked runs; have {len(iter_runs)}."

    last_iter = iter_runs[-1]
    prev_iter = iter_runs[-2]
    # Each iteration improvement is "this iter > the run immediately preceding it in `runs`"
    def predecessor(target_run: dict) -> dict | None:
        idx = next(i for i, r in enumerate(runs) if r["run_id"] == target_run["run_id"])
        return runs[idx - 1] if idx > 0 else None

    deltas = []
    for cur in (prev_iter, last_iter):
        pred = predecessor(cur)
        if pred is None:
            return False, f"Run {cur['run_id']} has no predecessor; cannot compute delta."
        d = _mean_fit(cur["run_id"], latest) - _mean_fit(pred["run_id"], latest)
        deltas.append((cur["run_id"], pred["run_id"], d))

    both_up = all(d > 0 for _, _, d in deltas)
    lines = [
        f"  {cur[:8]} vs {pred[:8]}: Δ mean fit = {d:+.3f}"
        for cur, pred, d in deltas
    ]
    banner = (
        f"Ship-gate {'PASS' if both_up else 'FAIL'} — last two iteration runs:\n"
        + "\n".join(lines)
    )
    return both_up, banner
```

The CLI wrapper at `apollo/scripts/eval_ship_check.py`:
```python
import sys
from apollo.eval.ship_check import check_ship_gate

def main(argv=None) -> int:
    passed, banner = check_ship_gate()
    print(banner)
    return 0 if passed else 1

if __name__ == "__main__":
    sys.exit(main())
```

**Note on "predecessor":** D-16 says "two consecutive iteration-marked runs both improved over their respective predecessors." The above interpretation = each iteration-marked run's delta is computed vs. the run that immediately precedes it in the `runs.jsonl` order (which may itself be a non-iteration run). This is the literal reading. **Planner should confirm with user** that "predecessor" means "previous row in runs.jsonl" and not "previous iteration-marked run" — both are defensible.

### Anti-Patterns to Avoid

- **DON'T store scores in CSV.** JSONL is what the user picked (D-08). CSV can't carry the optional free-text note cleanly (commas, newlines in notes break round-trip).
- **DON'T use SQLite for the score store.** Adds a binary file the user can't `cat`. The "git-diffable" rationale in D-08 explicitly favors JSONL.
- **DON'T mutate `scores.jsonl` to "fix" a duplicate.** Appending another line is the contract; consumers take the latest. Mutation breaks git-diffable history.
- **DON'T bind Flask to `0.0.0.0`.** Bind to `127.0.0.1`. The grader UI is single-user, local, and showing the network to other devices is a security smell.
- **DON'T attempt MIDI parsing inside the M4L device's JS.** Have `apollo eval render` write a `response.json` sidecar alongside each `response_001.mid` (list of {pitch, velocity, start_beats, end_beats}) and have the JS read that. Saves dozens of hours of M4L debugging.
- **DON'T compute the run hash from training script command-line args or git SHA.** That diverges from D-09 (which says: checkpoint bytes + corpus pair-IDs). Stick to D-09 exactly; git SHA and CLI args go in `runs.jsonl` as separate metadata fields if needed.
- **DON'T render audio "on demand" during grading.** D-07 is explicit: pre-rendered once per run. Grading must not touch Ableton.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTTP routing | Custom WSGI / http.server subclass | **Flask** | 5 routes worth of routing logic exceeds bare http.server's ergonomics |
| HTML templating | String concat with `f"..."` | **Jinja2** (Flask's default) | Comes free with Flask; avoids XSS escape mistakes |
| JSONL parsing in notebook | Manual `for line in open: json.loads(line)` | **`pd.read_json(path, lines=True)`** | One line; integrates with groupby/mean |
| Audio bounce inside Live | Custom OSC server triggering Live remote | **`[sfrecord~]` in M4L** | Standard Max idiom; signal-flow-native; no IPC |
| Hashing | Hand-rolled hash | **`hashlib.blake2b`** | Stdlib, deterministic, MUCH stronger than any hand-rolled variant |
| Score deduplication | Rewrite-on-conflict logic | **Append + last-line-wins on read** | Simpler write path; matches event-sourcing pattern |
| Notebook delta charts | Custom matplotlib boilerplate per cell | **pandas `groupby().mean().plot()`** | One-liners; user can riff in the notebook |

**Key insight:** Phase 4 is glue. Every component is a thin layer over a well-known library. Resist building "Apollo's grading framework" — there are 30 held-out pairs to score and the user wants a 10-minute experience.

## Runtime State Inventory

Phase 4 is greenfield (no rename/refactor). This section is included for completeness because Phase 4 *introduces* runtime state that future phases must be aware of:

| Category | Items Introduced | Action Required (future) |
|----------|------------------|---------------------------|
| Stored data | `eval/scores.jsonl`, `eval/runs.jsonl`, `data/pairs/NNN/eval/{run_id}/response.wav` | Document in `.gitignore`; back up before destructive operations on `data/pairs/` |
| Live service config | M4L device path attribute pointing to manifest JSON | If `m4l/ApolloRender.amxd` is moved, user must re-point in Live |
| OS-registered state | None | — |
| Secrets / env vars | None (Flask binds to 127.0.0.1, no auth) | — |
| Build artifacts | `eval/render_manifests/*.json` | Regenerable; can be deleted between iterations |

**Nothing found in other categories** — Phase 4 stays inside the repo and Ableton; no system-level registration.

## Blind Grading UX Patterns

**Hiding run/checkpoint metadata while still tracking it server-side:**

1. **Server-side state, not URL.** The run_id is passed to the Flask app at startup via CLI arg, stored in `app.config["RUN_ID"]`. Routes never echo it into HTML responses. `GET /pair/007` returns the *same HTML* regardless of which run is active — only the wav file served by `GET /audio/007/response.wav` differs.
2. **No metadata in DOM.** `pair.html` template does not render the run_id, checkpoint path, or timestamp. The page shows: pair NNN, two sliders, one note field, a submit button. That's it. (Pair NNN is *not* blind metadata — the user knows which gesture they authored — but model identity is hidden.)
3. **Randomization of presentation order.** The worklist (`GET /`) shuffles pair order using `random.Random(seed=hash(run_id)).shuffle(pairs)`. Deterministic per run (so resuming a session sees the same order) but different across runs (so the user can't memorize "I rated pair 007 a 4 last time").
4. **Reveal toggle.** A small "🔎 reveal" link at the bottom of each pair page calls `GET /reveal/<nnn>` (returns JSON `{run_id, ckpt, iteration}`), and JS injects a small overlay. Hitting it auto-logs a flag in the request log (`reveal_used: True` could go in the score record's note field for honesty tracking — but D-03 says note is freeform, so just leave it).

**The grader's "honor mode":** Since the user is both training target and grader, there's no enforcement against running `cat eval/runs.jsonl` outside the UI to peek. The blind-by-default + reveal toggle pattern is the *behavioral nudge*, not a security barrier. Surface this in the rubric.md docs.

## Common Pitfalls

### Pitfall 1: Flask dev server is not for "production" — but it IS fine for local single-user

**What goes wrong:** Flask's startup banner warns "WARNING: This is a development server." Users new to Flask think they need gunicorn/uvicorn.
**Why it happens:** Flask's docs are written for web-deployment audiences.
**How to avoid:** Document in the README that the dev server is intentional — single-user, localhost-only, no concurrent requests, no production traffic. `flask run` is correct.
**Warning signs:** None. The warning is informational, ignore it.

### Pitfall 2: JSONL line atomicity across multiple appends in one HTTP request

**What goes wrong:** `POST /score` appends TWO records (fit + coherence). If the process is killed between the two writes, the JSONL ends up with a "fit" record but no matching "coherence". The notebook sees one half of the submission.
**Why it happens:** Two `with open(...,"a")` calls = two filesystem writes; nothing atomic across them.
**How to avoid:** Either (a) write both lines from a single `open()` call before closing/flushing, or (b) accept the asymmetry — the notebook should treat missing dimensions gracefully (compute mean over whatever records exist). **Recommendation:** Option (a). Open once, write both lines, flush.
```python
with open(path, "a", encoding="utf-8") as f:
    f.write(json.dumps(fit_record) + "\n")
    f.write(json.dumps(coh_record) + "\n")
    f.flush()
```
**Warning signs:** Notebook shows pairs with one dim scored but not the other. If frequent, the atomic-write fix is needed.

### Pitfall 3: M4L device runs before Live set finishes loading

**What goes wrong:** Device starts walking the manifest before all Operator presets/clips are ready; first 1–2 bounces are silence.
**Why it happens:** `[live.thisdevice]` fires `bang` once the device is in a fully-loaded set, but custom scripts in `[js]` may try to access `LiveAPI` before this. Race.
**How to avoid:** Gate the manifest-walk start on the `live.thisdevice` bang. Don't auto-run on patch-loaded. Add a manual "Start" button as backup.
**Warning signs:** First wav in the run is silent; subsequent ones are fine.

### Pitfall 4: `[sfrecord~]` writes 32-bit float by default

**What goes wrong:** Default `[sfrecord~]` mode writes 32-bit float WAV, which some browsers' HTML5 `<audio>` element refuses to decode.
**Why it happens:** Web Audio standards prefer 16-bit PCM or 24-bit PCM. Some Chrome/Safari versions silently fail on 32-bit float WAV.
**How to avoid:** Instantiate as `[sfrecord~ 16]` (16-bit) or convert after the fact. **Recommendation:** `[sfrecord~ 16]` at the source.
**Warning signs:** `GET /audio/<nnn>/response.wav` returns the file but the browser shows "Failed to load audio."

### Pitfall 5: Path-traversal in the audio route

**What goes wrong:** `send_file(pairs_root / nnn / "call.wav")` with `nnn="../../etc/passwd"` would serve arbitrary files.
**Why it happens:** Flask `<nnn>` route variable is user-controlled.
**How to avoid:** Validate `nnn` matches `^[0-9A-Za-z_-]+$` (the discover_pairs pattern) before constructing paths. Or use `werkzeug.utils.safe_join`. Reuse Phase 1's `pairs.py:discover_pairs` enforcement — check the requested `nnn` is in the discovered set.
**Warning signs:** None at runtime; catch in code review.

### Pitfall 6: Notebook reads stale JSONL because Jupyter cached the import

**What goes wrong:** User runs the notebook, grades more pairs, re-runs the notebook — sees old data because pandas read once and the cell is cached.
**Why it happens:** Cell value caching in Jupyter, plus pandas DataFrame held in memory.
**How to avoid:** First cell of `delta.ipynb` always re-reads with `pd.read_json("eval/scores.jsonl", lines=True)`. Document at the top of the notebook: "Restart Kernel and Run All when you grade new sessions."
**Warning signs:** Notebook delta plot doesn't reflect just-graded pairs.

### Pitfall 7: Empty or missing JSONL files crash the loader

**What goes wrong:** First run, `runs.jsonl` doesn't exist yet; `pd.read_json` raises FileNotFoundError; `apollo eval ship-check` crashes.
**Why it happens:** No tool ever wrote to the file yet.
**How to avoid:** Wrap reads in `if not path.is_file(): return []` (see `_load_jsonl` above). Ship-check returns FAIL with helpful message when there's no data.
**Warning signs:** First-time-setup crash.

### Pitfall 8: Iteration marker confused with run ordinal

**What goes wrong:** User marks every run as `iteration: true`. Ship-gate logic then has too many candidates and the "consecutive" definition becomes ambiguous.
**Why it happens:** D-16 says "the user flags a run as iteration: true when they want it to count." Easy to over-mark.
**How to avoid:** Document in `rubric.md` and the CLI help: "Mark only the runs that represent a true corpus expansion / retraining round you want measured. Sweeps and debug runs stay `iteration: false`."
**Warning signs:** Ship-check banner shows confusing deltas.

## Rubric Schema

**File: `eval/rubric.md`** (committed to repo)

Structure (planner writes the actual prose; this is the contract):

```markdown
# Apollo Grading Rubric

## How to grade
1. Open the grading UI: `python -m apollo.scripts.eval_grade <pairs_root> --run-id <run_id>`
2. For each held-out pair: click play, listen call → response, slide both sliders, optionally note.
3. Submit advances to next pair. Sessions resume if interrupted.

## Dimensions

### Call-Response Fit (1–5) — THE SHIP-GATING DIMENSION
- **1** — Unrelated. The response could have followed any call.
- **2** — Marginally related. Some shared element (key, register, or rhythm) but no real call-and-response logic.
- **3** — Plausible response. Reasonable musical reply; nothing distinctive.
- **4** — Strong response. Clearly answers the call; choice I might make.
- **5** — Exactly what I'd play. Indistinguishable from my authoring intent.

### Musical Coherence (1–5) — TRACKED, NOT GATING
- **1** — Notes are wrong (out-of-scale-without-purpose, untuned, broken).
- **2** — Notes work but phrasing is awkward; timing or contour off.
- **3** — Coherent musical statement standalone.
- **4** — Good phrase shape, intentional timing.
- **5** — Could appear in a finished piece as-is.

## Free-text note
Optional. Useful patterns: "tonic-bound", "rhythm matches but pitch random", "second note feels late".
```

(Anchor wording above is *suggested*; user finalizes during plan-check.)

## Delta Notebook Structure

**File: `eval/delta.ipynb`**

Recommended cell sequence (each cell ≤ 5 lines):

1. **Imports + paths**
   ```python
   import pandas as pd, matplotlib.pyplot as plt
   from pathlib import Path
   SCORES = Path("eval/scores.jsonl"); RUNS = Path("eval/runs.jsonl")
   ```

2. **Load + dedup to latest-per-key**
   ```python
   scores = pd.read_json(SCORES, lines=True)
   runs = pd.read_json(RUNS, lines=True)
   scores = scores.drop_duplicates(subset=["run_id","pair_id","dim"], keep="last")
   ```

3. **Plot 1 — Per-dim mean over runs (REQUIRED)**
   ```python
   means = scores.groupby(["run_id","dim"])["score"].mean().unstack()
   means = means.reindex(runs.sort_values("created")["run_id"])  # chronological
   ax = means.plot(marker="o", figsize=(8,4))
   ax.set_xticklabels([r[:8] for r in means.index], rotation=45)
   ax.set_title("Mean score per dimension across runs"); plt.show()
   ```

4. **Plot 2 — Per-pair trajectories (REQUIRED)**
   ```python
   fit = scores[scores.dim=="fit"]
   pivot = fit.pivot_table(index="run_id", columns="pair_id", values="score")
   pivot = pivot.reindex(runs.sort_values("created")["run_id"])
   ax = pivot.plot(figsize=(10,5), legend=False, alpha=0.5)
   ax.set_title("Per-pair call-response-fit trajectory"); plt.show()
   ```

5. **Ship-gate explainer cell**
   ```python
   from apollo.eval.ship_check import check_ship_gate
   passed, banner = check_ship_gate()
   print(banner)
   ```

6. **(Optional) Bottom-N pairs by latest delta** — discretionary, helps identify gaps for next authoring round.
   ```python
   latest_fit = pivot.iloc[-1] - pivot.iloc[-2]
   print(latest_fit.sort_values().head(5))  # 5 most-regressed pairs
   ```

The notebook is the user's exploration surface (D-10 specifically wanted exploratory over static). Cells 5+ can be added/edited; cells 3 and 4 must remain as the canonical plots.

## CLI Subcommand Pattern

**Existing project convention** (verified from `apollo/scripts/`):
- One file per script under `apollo/scripts/`.
- Each script defines `main(argv=None) -> int` and an `if __name__ == "__main__": sys.exit(main())` guard.
- Invocation: `python -m apollo.scripts.<name>` or `venv/bin/python -m apollo.scripts.<name>`.
- **There is NO `apollo` console-script entry point in pyproject.toml.** The phrase "`apollo eval ship-check`" in CONTEXT.md is conceptual shorthand for `python -m apollo.scripts.eval_ship_check`.

**Planner decision point — surface explicitly:** Should Phase 4 add a `[project.scripts]` entry that maps `apollo` to a click/argparse-based dispatcher with subcommands (`apollo eval render`, `apollo eval grade`, `apollo eval ship-check`)? Two options:
- **(A) Stay with current pattern.** Phase 4 adds `eval_render.py`, `eval_grade.py`, `eval_ship_check.py` — three standalone scripts. CONTEXT.md's `apollo eval ship-check` is shorthand. Lowest cost; matches existing code shape.
- **(B) Add a real CLI dispatcher.** Add `apollo/cli.py` with `argparse.ArgumentParser(prog="apollo")` + subparsers; register `[project.scripts]` `apollo = "apollo.cli:main"`. Then `apollo eval ship-check` works literally. More work, but the wording in CONTEXT.md becomes accurate command syntax and `--help` discoverability improves.

**Recommendation:** **Option (A) for v1**, with a documentation alias in README ("the CLI commands described below are shorthand for `python -m apollo.scripts.<name>`"). Adding a real dispatcher is gold-plating for three subcommands. If the eval-tools surface grows, promote to Option (B) later.

## Code Examples

### Enumerate held-out pairs (verified pattern, reusing existing assets)
```python
# apollo/eval/heldout.py
from typing import List
from apollo.ingest.pairs import discover_pairs, PairPath
from apollo.ingest.split import is_heldout

def enumerate_heldout(pairs_root: str) -> List[PairPath]:
    """Return the deterministic held-out subset for `<pairs_root>`."""
    return [p for p in discover_pairs(pairs_root) if is_heldout(p.nnn)]
```
[VERIFIED: `discover_pairs` and `is_heldout` already exist in `apollo/ingest/` per Phase 1.]

### Write the run manifest
```python
# apollo/eval/runs_log.py
import json
from pathlib import Path
from datetime import datetime, timezone

def append_run(record: dict, path: str = "eval/runs.jsonl") -> None:
    """Append one run record. `record` must include run_id, checkpoint_hash,
    train_pair_ids (list), iteration (bool), and any planner-chosen extras."""
    record.setdefault("created", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, separators=(",", ":")) + "\n")
        f.flush()
```

### Recommended `runs.jsonl` record schema
```json
{
  "run_id": "a3f1c0d2e9b78544",
  "created": "2026-05-21T14:32:18Z",
  "checkpoint_path": "models/run-02-20260521T143218Z.pt",
  "checkpoint_hash": "<sha256 of checkpoint bytes, full 64 chars — for verification, not identity>",
  "train_pair_ids": ["001","002","004","005","..."],
  "n_train_pairs": 30,
  "n_heldout_pairs": 8,
  "iteration": true,
  "iteration_label": "iter-02",          // optional, human label
  "training_epochs": 300,
  "training_lr": 0.001,
  "git_sha": "4cad8ac",                  // optional
  "notes": ""                            // user-supplied at render time
}
```

**Planner picks** which fields are MUST vs MAY. At a minimum (per D-08): run_id, checkpoint_hash, train_pair_ids, iteration, created. Everything else is helpful but not load-bearing.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The single canonical "response.mid" per held-out pair per run is `response_001.mid` (generate.py's first output). | Project Constraints | MEDIUM — if user wants to grade N-sampled responses, the manifest schema needs to carry N entries per pair. Recommend confirming in plan-check. |
| A2 | "Predecessor" in D-16 = immediately-previous row in `runs.jsonl` (not "previous iteration-marked run"). | Pattern 5 | MEDIUM — ship-gate semantics depend on this. Surface for user confirmation. |
| A3 | Live 12 LOM does not expose a Set-level programmatic batch export; `[sfrecord~]` is the practical path. | Pattern 4 | MEDIUM — if a hidden API exists that the user discovers, the device gets simpler. Recommend a 30-min spike inside Live to confirm before committing the device design. |
| A4 | A JSON sidecar (per-clip note list) is easier than parsing MIDI in the M4L device's JS. | Pattern 4 + Anti-Patterns | LOW — even if JS MIDI parsing turns out fine, the sidecar approach is strictly simpler. |
| A5 | Flask 3 development server is acceptable for single-user local grading. | Standard Stack | VERY LOW — explicit Flask recommendation in docs for exactly this case. |
| A6 | The user is on macOS and POSIX append-line atomicity holds. | Pattern 1 | VERY LOW — CLAUDE.md confirms Apple Silicon (macOS). |
| A7 | `blake2b(digest_size=8)` 16-hex-char run IDs have negligible collision risk over realistic iteration counts (<1000 runs). | Pattern 2 | VERY LOW — 64-bit hash, birthday-bound collision at ~2³². |
| A8 | M4L device sample rate matches Live's set rate (44100 Hz typical). | Pattern 4 | LOW — Live's default; if user runs at 48 kHz, `[sfrecord~]` should match dynamically via `live.thisdevice`'s reported SR. |
| A9 | The grader's "blind" status is honor-system, not security-enforced. | Blind Grading UX | NEGLIGIBLE — explicitly accepted in CONTEXT.md framing ("user is both training target and grader"). |
| A10 | Held-out pair count of ~6 (20% of 30) is small enough that all-pairs-per-session (D-06) is feasible. | Web UI | NEGLIGIBLE — math holds. |

## Open Questions

1. **N-sampled response.mid grading.** Phase 3 D-17 supports `--n` for multiple response samples per call. Does Phase 4 grade only `response_001.mid`, or grade all N and use the mean / best?
   - What we know: D-07 says "pre-rendered once per run" — singular.
   - What's unclear: Whether the singular "once" refers to "one wav per pair" or "one rendering session."
   - Recommendation: Default to grading `response_001.mid` only. If user runs with `--n > 1` in generate.py, write a clear note that subsequent responses are ignored by Phase 4. Promote to a v2 feature ("grade best-of-N").

2. **Predecessor semantics for ship-gate.** See A2 above.
   - Recommendation: Plan-check question for user. Both readings are defensible; the literal reading (immediate predecessor in runs.jsonl) is what the code above implements.

3. **Where the M4L device finds its manifest.** Hardcoded path inside the device patch vs. configurable via a device parameter?
   - What we know: D-13 says "coordinate via folder convention."
   - Recommendation: Hardcode `../../eval/render_manifests/active.json` relative to the device, and have `apollo eval render` write the manifest to that fixed path (overwriting). One source of truth, no UI plumbing needed.

4. **Iteration marker UX.** D-16 says "the user flags a run as iteration: true when they want it to count." How does the user set this?
   - Option (a): CLI flag on `apollo eval render --iteration` writes `iteration: true` to the runs.jsonl entry at render time.
   - Option (b): User hand-edits runs.jsonl post-hoc.
   - Recommendation: Option (a). One flag at render time. Hand-editing JSONL is a footgun.

5. **`call.wav` source.** Phase 1's `data/pairs/NNN/call.wav` is the user's hand-bounced original audio. Does Phase 4's grader play that exact file, or play a per-run rendered call.wav?
   - What we know: The call timbre is conditioning, not generation. Same call.wav across runs.
   - Recommendation: Play `data/pairs/NNN/call.wav` (the original, shared across runs). Only `response.wav` is per-run.

6. **What happens if a held-out pair has no `response_001.mid`?**
   - The M4L manifest builder should skip that pair and log a warning.
   - The web UI worklist marks it as "no response generated — re-run generate.py."

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11+ | All Python tooling | ✓ | (assumed per pyproject.toml `requires-python = ">=3.11"`) | — |
| pip / venv | Install Flask + pandas | ✓ | — | — |
| Flask | Web UI | ✗ (not yet) | install: `pip install flask` | None acceptable — pure-stdlib alternative is `http.server` subclass and is more work |
| pandas | Notebook | ✗ (not yet) | install: `pip install pandas` | Stdlib JSON + manual aggregation (workable but ugly) |
| matplotlib | Notebook | ✗ (not yet) | install: `pip install matplotlib` | None — required for D-10 |
| jupyter | Notebook | ✗ (not yet) | install: `pip install jupyter` | jupyterlab is equivalent |
| **Ableton Live 11 or 12** | M4L device runtime | ✓ (presumed; user authors in Ableton per PROJECT.md) | — | None — Phase 4 requires Live |
| **Max for Live** | M4L device build + load | ✓ (presumed; comes with Ableton Live Suite) | — | None — required for the .amxd |
| Max 8/9 (standalone, for editing the device) | Building/editing `.amxd` | Maybe; verify with user | — | The device can be edited inside Live's M4L editor if standalone Max isn't installed |

**Missing dependencies with no fallback:** None blocking. All Python deps are `pip install`.

**Missing dependencies with fallback:** All listed above for the eval Python stack.

**Recommendation:** Add the `eval` extra to pyproject.toml and document a single `pip install -e ".[eval]"` step in the phase plan.

## Sources

### Primary (HIGH confidence)
- Existing repo code: `apollo/ingest/split.py`, `apollo/ingest/pairs.py`, `apollo/scripts/train.py`, `apollo/scripts/generate.py` — verified by direct read
- Python stdlib: `hashlib.blake2b` — https://docs.python.org/3/library/hashlib.html#blake2 — digest_size parameter, deterministic across platforms
- Flask quickstart + application factory pattern — https://flask.palletsprojects.com/en/3.0.x/tutorial/factory/
- pandas `read_json(lines=True)` — https://pandas.pydata.org/docs/reference/api/pandas.read_json.html
- Phase 1 RESEARCH.md (style/structure reference) and Phase 2 RESEARCH.md (style reference, checkpoint format)

### Secondary (MEDIUM confidence)
- Max for Live / Live Object Model documentation — https://docs.cycling74.com/legacy/max8/vignettes/live_object_model — `[sfrecord~]`, `[live.thisdevice]`, JS `LiveAPI` patterns. Backward-compatible across Live 11/12.
- POSIX append-write atomicity for short lines — well-documented stdlib behavior, no single canonical URL

### Tertiary (LOW confidence / ASSUMED)
- Live 12 has no public batch-export-audio API. Based on absence in published LOM docs; could be wrong if a recent undocumented method exists. **Recommend 30-min in-Live spike during plan-check to confirm.**
- 4 KB PIPE_BUF threshold for POSIX atomic writes — true for most filesystems but not formally tested against the user's APFS volume.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| CSV for tabular score data | JSONL (one JSON per line) | ~2018 onwards for ML evaluation data | Carries optional/structured fields (notes, metadata) without quote-escape hell; appends atomically |
| Tk / wxPython local desktop apps | Local Flask + browser tab | ~2015 onwards | Browser is the universal UI; HTML5 `<audio>` is free; styling is CSS not native widgets |
| MD5 / SHA-1 for content IDs | blake2b with configurable digest_size | Python 3.6+ | Faster + stronger; no slicing ceremony |
| Live API via OSC bridges (live.osc) | M4L device using JS LiveAPI directly | Live 9+ | In-process, no IPC, signal-flow-native |

**Deprecated:** None of the prior approaches are "wrong"; they're just heavier than what Phase 4 needs.

## Metadata

**Confidence breakdown:**
- Web UI / Flask stack: HIGH — well-trodden, ~150 LOC for 5 routes
- JSONL persistence + run-id hash: HIGH — pure Python stdlib, fully testable
- Ship-gate logic: HIGH — pure function, CI-testable, no I/O surprises
- Notebook: HIGH — pandas + matplotlib are standard
- M4L device design: MEDIUM — `[sfrecord~]` approach is sound but Live's LOM has undocumented edges; recommend 30-min spike before locking the device design
- CLI subcommand wiring: HIGH — the project's existing pattern is unambiguous; just add three more scripts

**Research date:** 2026-05-21
**Valid until:** 2026-06-21 (30 days; Flask/pandas/matplotlib are stable, Live 12 API may receive updates but unlikely to invalidate `[sfrecord~]`)
