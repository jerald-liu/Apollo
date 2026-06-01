# Phase 4: Evaluation Loop — Pattern Map

**Mapped:** 2026-05-21
**Files analyzed:** 22 new files (11 Python modules, 3 CLI scripts, 5 tests, 2 Jinja templates, 1 CSS, 1 JS, plus committed `eval/rubric.md`, `eval/delta.ipynb`, `m4l/ApolloRender.amxd` + README)
**Analogs found:** 18 / 22 (4 have no in-repo analog — Flask app/templates/JS/M4L device — these fall back to RESEARCH.md §Pattern 3 & §Pattern 4)

---

## File Classification

| New / Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `apollo/eval/__init__.py` | package | re-export | `apollo/ingest/__init__.py` | exact |
| `apollo/eval/heldout.py` | utility | transform | `apollo/ingest/split.py` + `apollo/ingest/pairs.py` (composition) | exact |
| `apollo/eval/run_id.py` | utility | transform (pure hash) | `apollo/ingest/split.py` (sha1 idiom) | role+flow match |
| `apollo/eval/runs_log.py` | persistence | append-only file I/O | `apollo/model/train.py:save_checkpoint` + `apollo/scripts/train.py` CSV writer | role match (append vs overwrite) |
| `apollo/eval/scores_log.py` | persistence | append-only file I/O | `apollo/model/train.py:save_checkpoint` (atomic write contract) | role match |
| `apollo/eval/ship_check.py` | service | request-response (pure fn over JSONL) | `apollo/ingest/artifact.py:ingest` (pure orchestration over readers) | role match |
| `apollo/eval/render_manifest.py` | service | transform → file I/O | `apollo/ingest/artifact.py` (composes discover_pairs + write) | role match |
| `apollo/eval/web/__init__.py` | package | re-export | `apollo/ingest/__init__.py` | exact |
| `apollo/eval/web/app.py` | controller (HTTP) | request-response | **no in-repo analog** — see RESEARCH §Pattern 3 | fallback |
| `apollo/eval/web/templates/index.html` | view (Jinja) | request-response | **no in-repo analog** | fallback |
| `apollo/eval/web/templates/pair.html` | view (Jinja) | request-response | **no in-repo analog** | fallback |
| `apollo/eval/web/static/grade.js` | view (browser) | event-driven | **no in-repo analog** | fallback (UI-SPEC §Interaction Contract) |
| `apollo/eval/web/static/style.css` | view (styling) | static | **no in-repo analog** | fallback (UI-SPEC §Color/§Typography/§Spacing) |
| `apollo/scripts/eval_render.py` | CLI script | request-response | `apollo/scripts/generate.py` + `apollo/scripts/ingest_corpus.py` | exact |
| `apollo/scripts/eval_grade.py` | CLI script | request-response (spawns Flask) | `apollo/scripts/generate.py` (CLI shape) + RESEARCH §Pattern 3 (Flask launch) | partial |
| `apollo/scripts/eval_ship_check.py` | CLI script | request-response | `apollo/scripts/ingest_corpus.py` (thinnest existing CLI) | exact |
| `tests/test_run_id.py` | test | n/a | `tests/test_split_determinism.py` | exact |
| `tests/test_ship_check.py` | test | n/a | `tests/test_split_determinism.py` (pure-function determinism) + `tests/test_generate.py` (CLI exit-code style) | role match |
| `tests/test_scoring.py` | test (JSONL I/O) | n/a | `tests/test_checkpoint.py` (round-trip) + `tests/test_ingest_smoke.py` (tmp_path I/O) | role match |
| `tests/test_render_manifest.py` | test | n/a | `tests/test_ingest_smoke.py` (synthesize_pair + run pipeline + assert) | role match |
| `tests/test_eval_web.py` | test (Flask) | n/a | `tests/test_generate.py` (CLI smoke via `.main([...])`) — adapt for Flask test client | partial |
| `pyproject.toml` (modified) | config | static | existing `[project.optional-dependencies]` block | exact |
| `eval/rubric.md` (committed) | docs | static | none (project's first user-facing rubric) | n/a |
| `eval/delta.ipynb` (committed) | notebook | transform → plot | none in repo | fallback (RESEARCH §Delta Notebook Structure) |
| `m4l/ApolloRender.amxd` (binary) | device | streaming (real-time audio capture) | none | fallback (RESEARCH §Pattern 4) |
| `m4l/ApolloRender.README.md` | docs | static | none | n/a |

---

## Pattern Assignments

### `apollo/eval/__init__.py` (package re-export)

**Analog:** `apollo/ingest/__init__.py`

**Pattern to copy** (full file, lines 1–39):
```python
"""Apollo ingest package — pair discovery, MIDI/audio loading, split, artifact.

Public surface:
    - IngestError          (exception used throughout the pipeline)
    - ...
"""

from .artifact import SCHEMA_VERSION, ingest, load_artifact, save_artifact
from .audio import MelExtractor
from .errors import IngestError
...

__all__ = [
    "IngestError",
    ...
]
```

**Apply to eval:** docstring lists public surface; re-export `compute_run_id`, `enumerate_heldout`, `append_run`, `append_score`, `load_scores`, `check_ship_gate`, `write_render_manifest`. Mirror the `__all__` convention exactly.

---

### `apollo/eval/heldout.py` (utility, transform)

**Analog:** `apollo/ingest/split.py` (sha1 idiom) + `apollo/ingest/pairs.py` (PairPath consumer)

**Composition pattern** — RESEARCH §"Enumerate held-out pairs" already specifies:
```python
from typing import List
from apollo.ingest.pairs import discover_pairs, PairPath
from apollo.ingest.split import is_heldout

def enumerate_heldout(pairs_root: str) -> List[PairPath]:
    """Return the deterministic held-out subset for `<pairs_root>`."""
    return [p for p in discover_pairs(pairs_root) if is_heldout(p.nnn)]
```

**Module docstring style — copy from `apollo/ingest/split.py` lines 1–12:**
```python
"""Deterministic hash-based held-out split.

See .planning/phases/01-tokenizer-ingest/01-RESEARCH.md §"Deterministic Split"
and CONTEXT.md D-20. ...
"""
from __future__ import annotations
```

Apply: lead with `from __future__ import annotations`, link back to `.planning/phases/04-evaluation-loop/04-RESEARCH.md` and the relevant D-number.

---

### `apollo/eval/run_id.py` (utility, pure hash)

**Analog:** `apollo/ingest/split.py` (sha1 + module-level pure-function style)

**Hashing pattern** — `apollo/ingest/split.py` lines 32–39:
```python
def is_heldout(nnn: str, k: int = 5) -> bool:
    s = normalize_nnn(nnn)
    h = int(hashlib.sha1(s.encode("utf-8")).hexdigest(), 16)
    return (h % k) == 0
```

**Apply to run_id (copy RESEARCH §Pattern 2 verbatim):**
```python
import hashlib
from pathlib import Path
from typing import Iterable

def compute_run_id(checkpoint_path: str, train_pair_ids: Iterable[str]) -> str:
    h = hashlib.blake2b(digest_size=8)
    p = Path(checkpoint_path)
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            h.update(chunk)
    h.update(b"\x00CORPUS\x00")
    for pid in sorted(train_pair_ids):
        h.update(pid.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()
```

**Convention to copy from split.py:** module docstring cites the relevant research section and decision IDs (D-09); `from __future__ import annotations` at top; pure-function style with one-paragraph docstring per public function.

---

### `apollo/eval/runs_log.py` (persistence, append-only)

**Analog:** `apollo/model/train.py:save_checkpoint` (lines 155–180) — the project's existing "write a structured record to disk" function.

**Pattern from save_checkpoint** (lines 169–180) — `out.parent.mkdir(parents=True, exist_ok=True)` + `torch.save(...)`:
```python
def save_checkpoint(...) -> None:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    torch.save({...}, str(out))
```

**Apply to runs_log** (RESEARCH §"Write the run manifest" + Pitfall 2):
```python
import json
from pathlib import Path
from datetime import datetime, timezone

def append_run(record: dict, path: str = "eval/runs.jsonl") -> None:
    record.setdefault("created", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, separators=(",", ":")) + "\n")
        f.flush()
```

**Cross-cutting conventions enforced here:**
- `mkdir(parents=True, exist_ok=True)` before writing — matches `save_checkpoint` line 170 and `save_artifact` (`apollo/ingest/artifact.py` line 141)
- ISO UTC timestamp via `datetime.now(timezone.utc).isoformat(timespec="seconds")` — adapted from `apollo/scripts/train.py` line 150 (`strftime("%Y%m%dT%H%M%SZ")`); ISO form is friendlier for JSONL / pandas

---

### `apollo/eval/scores_log.py` (persistence, append-only)

**Analog:** same as runs_log.py (`save_checkpoint` + `save_artifact` for the mkdir/write convention)

**Pattern (RESEARCH §Pattern 1, lines 269–286) — copy verbatim:**
```python
def append_score(run_id: str, pair_id: str, dim: str, score: int,
                 note: str = "", path: str = "eval/scores.jsonl") -> None:
    assert dim in {"fit", "coherence"}, f"unknown dim {dim!r}"
    assert 1 <= score <= 5, f"score {score} outside 1..5"
    record = {
        "run_id": run_id, "pair_id": pair_id, "dim": dim, "score": score,
        "note": note,
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, separators=(",", ":")) + "\n")
        f.flush()
```

**CRITICAL — Pitfall 2 in RESEARCH:** Provide a `append_score_pair(run_id, pair_id, fit, coherence, note)` that opens the file ONCE and writes BOTH dim lines before close/flush, so `POST /score` is atomic per submit:
```python
with open(path, "a", encoding="utf-8") as f:
    f.write(json.dumps(fit_record, separators=(",", ":")) + "\n")
    f.write(json.dumps(coh_record, separators=(",", ":")) + "\n")
    f.flush()
```

**Loader pattern (mirror `_load_jsonl` from RESEARCH §Pattern 5, lines 439–443):**
```python
def load_scores(run_id: str | None = None, path: str = "eval/scores.jsonl") -> list[dict]:
    if not Path(path).is_file():
        return []
    with open(path, encoding="utf-8") as f:
        recs = [json.loads(line) for line in f if line.strip()]
    if run_id is not None:
        recs = [r for r in recs if r["run_id"] == run_id]
    return recs
```

The empty-file guard matches `apollo/ingest/artifact.py:load_artifact` defensive style (line 145 area).

---

### `apollo/eval/ship_check.py` (service, pure function)

**Analog:** `apollo/ingest/artifact.py:ingest` (pure orchestration that composes loaders + transforms)

**Pattern to copy verbatim from RESEARCH §Pattern 5 (lines 432–495):**
```python
from typing import List, Tuple
import json
from pathlib import Path

def _load_jsonl(path: str) -> List[dict]:
    if not Path(path).is_file():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]

def _latest_scores_per_run(scores: List[dict]) -> dict:
    out = {}
    for rec in scores:
        out[(rec["run_id"], rec["pair_id"], rec["dim"])] = rec["score"]
    return out

def check_ship_gate(runs_path: str = "eval/runs.jsonl",
                    scores_path: str = "eval/scores.jsonl") -> Tuple[bool, str]:
    # ... (see RESEARCH lines 458–494 for full body)
```

**Style note from `apollo/ingest/artifact.py`:** module docstring identifies the API contract (line 1–11); use `from __future__ import annotations`; private helpers prefixed with `_`.

**Open question to surface at plan time (RESEARCH A2):** "predecessor" semantics — confirm with user whether predecessor = previous row in `runs.jsonl` (literal reading, what the pattern implements) or previous iteration-marked run.

---

### `apollo/eval/render_manifest.py` (service, transform → file)

**Analog:** `apollo/ingest/artifact.py:ingest` (lines 72–131) — same shape: discover pairs, build a list of dicts, write a single output file.

**Composition pattern from artifact.py (lines 83–131):**
```python
def ingest(root: str, tempo_bpm: float = 120.0) -> dict:
    vocab = Vocab()
    mel_extractor = MelExtractor()
    pairs_paths = discover_pairs(root)
    entries = []
    for pp in pairs_paths:
        # ... per-pair work, append to entries
    return {"schema_version": ..., "pairs": entries, "metadata": {...}}
```

**Apply to render_manifest:**
```python
from pathlib import Path
import json
from apollo.eval.heldout import enumerate_heldout

def write_render_manifest(run_id: str, pairs_root: str,
                          manifest_path: str = "eval/render_manifests/active.json") -> Path:
    heldout = enumerate_heldout(pairs_root)
    entries = []
    for pp in heldout:
        response_mid = pp.dir / "response_001.mid"   # RESEARCH A1: first response only
        if not response_mid.is_file():
            continue                                 # RESEARCH Open Q #6: skip + log
        out_wav = pp.dir / "eval" / run_id / "response.wav"
        entries.append({
            "nnn": pp.nnn,
            "response_mid": str(response_mid),
            "out_wav": str(out_wav),
            # JSON sidecar of notes — see RESEARCH §Pattern 4 Pitfall 1
            "notes_json": str(response_mid.with_suffix(".notes.json")),
        })
    out = Path(manifest_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"run_id": run_id, "entries": entries}, indent=2))
    return out
```

**Pattern reuse:** uses `enumerate_heldout` (which itself uses `discover_pairs` + `is_heldout`) — single source of truth for "which pairs are eval-eligible," matching the project's "reuse existing assets" insight in CONTEXT §"Reusable Assets".

---

### `apollo/eval/web/app.py` (controller, HTTP request-response)

**Analog:** None in-repo (no Flask app exists yet). Use RESEARCH §Pattern 3 as ground truth.

**Pattern to copy verbatim from RESEARCH lines 336–387** — full `create_app()` factory.

**Conventions imported from elsewhere in repo:**

1. **Path-traversal guard (RESEARCH Pitfall 5)** — reuse `apollo/ingest/pairs.py:discover_pairs` (lines 41–99) style: resolve user-supplied path components and verify they remain inside `pairs_root`. Excerpt from pairs.py lines 68–75:
```python
resolved = entry.resolve()
try:
    resolved.relative_to(root_path)
except ValueError:
    raise IngestError(str(entry), "path traversal: ...")
```
Adapt: validate `nnn` against `enumerate_heldout(...)` set membership before `send_file`.

2. **Bind to 127.0.0.1 only** (RESEARCH §Anti-Patterns + UI-SPEC §Scope Framing).

3. **No autoplay** — JS file controls audio sequencing (UI-SPEC §Interaction Contract / Audio playback).

---

### `apollo/eval/web/templates/index.html` + `pair.html` + `static/grade.js` + `static/style.css`

**Analog:** None in repo. Full contract is in `04-UI-SPEC.md`.

**Planner / executor must follow UI-SPEC sections:**
- `index.html`: §Layout / "GET / — Worklist" + §Copywriting Contract (rows 1–6) + §Color tokens
- `pair.html`: §Layout / "GET /pair/<nnn>" + §Typography + §Copywriting Contract (rows 4–14)
- `grade.js`: §Interaction Contract / "Audio playback" + "Keyboard shortcuts" + "Submit semantics"
- `style.css`: §Color (CSS custom properties under `:root`) + §Spacing Scale + §Typography (3 roles, 2 weights)

**No icons except Unicode glyphs** (▶ ⏸ ⟳ 🔎 ✓ ·).

---

### `apollo/scripts/eval_render.py` (CLI script)

**Analog:** `apollo/scripts/generate.py` (full file) + `apollo/scripts/ingest_corpus.py` (thin shape)

**CLI scaffold pattern — copy from `apollo/scripts/generate.py` lines 116–215:**

Imports + main() + `if __name__ == "__main__": sys.exit(main())`:
```python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# ... domain imports

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="...")
    parser.add_argument("checkpoint", help="...")
    parser.add_argument("--iteration", action="store_true",
                        help="Mark this run as iteration:true in runs.jsonl (D-16)")
    args = parser.parse_args(argv)
    try:
        # ... domain work
        return 0
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"UNEXPECTED ERROR: {e!r}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    sys.exit(main())
```

**Exit-code contract (copy from `apollo/scripts/ingest_corpus.py` lines 7–11 docstring):**
- 0 = success
- 1 = known per-pair failure / missing file
- 2 = unexpected exception

**Module docstring style — `apollo/scripts/generate.py` lines 1–14 + `train.py` lines 1–10:** lead paragraph describes requirement IDs delivered (EVAL-IDs), then list of relevant D-decisions.

**Workflow for eval_render:**
1. Load checkpoint via `apollo.model.train.load_checkpoint` (lines 183–190 — same call shape as `generate.py` line 152)
2. Read `train_pair_ids` from the checkpoint's vocab/artifact metadata OR re-derive by listing `pairs_root` excluding held-out
3. `run_id = compute_run_id(ckpt_path, train_pair_ids)`
4. `append_run({run_id, checkpoint_path, checkpoint_hash, train_pair_ids, iteration: args.iteration, ...})`
5. `write_render_manifest(run_id, pairs_root)`

---

### `apollo/scripts/eval_grade.py` (CLI script that starts Flask)

**Analog:** `apollo/scripts/generate.py` for CLI scaffold + RESEARCH §Pattern 3 for the Flask launch line.

**CLI shape — same as `generate.py` above.** Body:
```python
from apollo.eval.web.app import create_app

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Launch the Apollo grading web UI.")
    parser.add_argument("pairs_root", help="data/pairs/ directory")
    parser.add_argument("--run-id", required=True, help="run_id from runs.jsonl")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args(argv)
    app = create_app(pairs_root=args.pairs_root, run_id=args.run_id)
    app.run(host="127.0.0.1", port=args.port, debug=False)
    return 0
```

**Bind host 127.0.0.1 explicitly** (RESEARCH §Anti-Patterns).

---

### `apollo/scripts/eval_ship_check.py` (CLI script)

**Analog:** `apollo/scripts/ingest_corpus.py` (lines 22–55) — the thinnest existing CLI; perfect template for "compute one thing, print result, exit with status."

**Pattern to copy (RESEARCH §Pattern 5 wrapper, lines 497–509):**
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

**Convention from `ingest_corpus.py`:** module docstring lists exit codes explicitly (lines 6–11 of ingest_corpus.py). Apply the same — document `0 = gate met`, non-zero otherwise (and what each non-zero means).

---

## Test Pattern Assignments

### `tests/test_run_id.py`

**Analog:** `tests/test_split_determinism.py` (the project's canonical "pure-function determinism" test file)

**Pattern to copy from test_split_determinism.py lines 1–48:**

1. **Module docstring identifies the contract being pinned** (lines 1–9):
```python
"""Tests for deterministic hash-based held-out split (DATA-04).

... This test file is the contract that pins that exact formula —
any change here means existing held-out assignments shift, ...
"""
```
Apply: pin the `compute_run_id` formula — "any change here invalidates all existing runs.jsonl entries."

2. **Determinism-across-calls test (lines 20–24):**
```python
def test_is_heldout_deterministic_across_calls():
    value = is_heldout("001")
    for _ in range(10):
        assert is_heldout("001") == value
```
Apply: `test_compute_run_id_deterministic_across_calls` — same checkpoint bytes + same pair IDs → same hash, 10x.

3. **Formula pin (lines 27–38):** rebuild the expected hash via raw `hashlib.blake2b` to confirm `compute_run_id` matches the literal byte-stream the docstring promises.

4. **Add:** test that order of `train_pair_ids` does NOT affect hash (`sorted()` semantics from RESEARCH Pattern 2).

---

### `tests/test_ship_check.py`

**Analog:** `tests/test_split_determinism.py` (pure-function style) + `tests/test_generate.py` lines 108–117 (CLI exit-code pattern)

**Pattern from test_generate.py for exit code assertion (lines 108–117):**
```python
def test_generate_missing_call_mid_returns_error(mock_ckpt, tmp_path):
    rc = generate.main([
        str(ckpt_path),
        str(tmp_path / "does_not_exist.mid"),
        ...
    ])
    assert rc != 0
```

**Apply to ship_check** — create synthetic `runs.jsonl` + `scores.jsonl` in tmp_path, call `check_ship_gate(runs_path=..., scores_path=...)`, assert `(passed, banner)`. CI cases per CONTEXT §"CI Coverage for Phase 4":
- Gate trips on two consecutive iteration-marked improvements
- Doesn't trip on one improvement only
- Ignores non-iteration-marked runs in the "is this an iteration boundary" decision
- Handles ties correctly (D-14: "up by any ε" — exact tie is NOT improvement)
- Empty runs.jsonl → returns False with informative message (RESEARCH Pitfall 7)

---

### `tests/test_scoring.py`

**Analog:** `tests/test_checkpoint.py` (round-trip pattern) + `tests/test_ingest_smoke.py` (tmp_path I/O pattern)

**Round-trip pattern from test_checkpoint.py:** save → load → assert equivalence. Adapt for JSONL: `append_score(...)` × N → `load_scores(...)` → assert all N records present.

**JSONL invariants per CONTEXT §"CI Coverage":**
- Append-only — second submit for same (run_id, pair_id, dim) produces 2 lines, not 1
- Latest-wins on read (`load_scores` last-write-wins semantics from RESEARCH Pattern 1)
- Atomic two-line submit (Pitfall 2): kill-after-first-line scenario impossible because both writes share one `open()`

**tmp_path style from test_ingest_smoke.py lines 26–30:** all I/O goes through `tmp_path` fixture; never write into the real `eval/` directory during tests.

---

### `tests/test_render_manifest.py`

**Analog:** `tests/test_ingest_smoke.py` (lines 26–60) — "synthesize fixture pairs, run pipeline, assert artifact shape"

**Pattern to copy from test_ingest_smoke.py:**
```python
def test_ingest_ten_pairs_end_to_end(tmp_path):
    for i in range(10):
        synthesize_pair(tmp_path, nnn=f"{i:03d}")
    artifact = ingest(str(tmp_path))
    assert artifact["schema_version"] == 1
    assert len(artifact["pairs"]) == 10
    # ... shape assertions
```

**Apply:** synthesize N mock pairs via `apollo.ingest.mock.synthesize_pair` (already in repo), touch `response_001.mid` files in the held-out subset, call `write_render_manifest(...)`, assert manifest entries match expected held-out NNNs only.

**Skip-on-missing-response case (RESEARCH Open Q #6):** create a pair WITHOUT `response_001.mid` and assert the manifest skips it (does not crash).

---

### `tests/test_eval_web.py`

**Analog:** `tests/test_generate.py` for `.main([...])`-style smoke + Flask's standard `app.test_client()`.

**Pattern (from RESEARCH §"CI Coverage for Phase 4"):**
- `GET /` returns held-out list
- `GET /pair/<nnn>` returns 200 for valid nnn, 404 for non-existent
- `POST /score` with valid JSON appends exactly two lines to `eval/scores.jsonl`
- Path-traversal: `GET /audio/..%2F..%2Fetc%2Fpasswd/call.wav` returns 4xx (Pitfall 5)

**Test client construction (Flask idiom):**
```python
from apollo.eval.web.app import create_app
def test_index_returns_worklist(tmp_path):
    # synthesize fixture pairs in tmp_path, then:
    app = create_app(pairs_root=str(tmp_path), run_id="testrun00000000")
    with app.test_client() as c:
        r = c.get("/")
        assert r.status_code == 200
```

---

### `pyproject.toml` (modification, not creation)

**Existing pattern** (lines 12–18 + 20–21):
```toml
dependencies = [
    "torch>=2.8.0",
    ...
]

[project.optional-dependencies]
dev = ["pytest>=7.0"]
```

**Add `eval` extra** per RESEARCH §Standard Stack:
```toml
[project.optional-dependencies]
dev = ["pytest>=7.0"]
eval = ["flask>=3.0", "pandas>=2.0", "matplotlib>=3.7", "jupyter>=1.0"]
```

---

## Shared Patterns (Cross-Cutting)

### S1. Module-level scaffolding (every new `.py` file)

**Source:** `apollo/ingest/split.py` lines 1–17, `apollo/ingest/pairs.py` lines 1–24, `apollo/ingest/artifact.py` lines 1–28.

**Apply to:** every file in `apollo/eval/` and `apollo/scripts/eval_*.py`.

**Required scaffold:**
```python
"""<one-line summary>.

<paragraph linking to .planning/phases/04-evaluation-loop/04-RESEARCH.md
 §<section> and CONTEXT.md D-<number>.>

<optional second paragraph for guarantees / contracts.>
"""

from __future__ import annotations

import <stdlib>
...

from apollo.<...> import <...>
```

Three-block import order (stdlib → third-party → first-party) per existing files. `from __future__ import annotations` is present in every Phase-1/2/3 module — Phase-4 must continue.

---

### S2. CLI exit-code contract

**Source:** `apollo/scripts/ingest_corpus.py` lines 1–13 (docstring) and lines 43–55 (try/except).

**Apply to:** `eval_render.py`, `eval_grade.py`, `eval_ship_check.py`.

**Required:**
- `def main(argv=None) -> int:` — accepts `argv` for testability
- `if __name__ == "__main__": sys.exit(main())` guard at bottom
- Three exit codes: 0 success, 1 known/expected failure, 2 unexpected exception
- Error messages go to `stderr` via `print(..., file=sys.stderr)`; never raise tracebacks at users

**Excerpt (ingest_corpus.py lines 43–55):**
```python
try:
    artifact = ingest(args.pairs_root, tempo_bpm=args.tempo_bpm)
    save_artifact(artifact, args.output)
    print(f"OK: {n} pairs ({h} heldout) -> {args.output}")
    return 0
except IngestError as e:
    print(f"INGEST FAILED: {e}", file=sys.stderr)
    return 1
except Exception as e:
    print(f"UNEXPECTED ERROR: {e!r}", file=sys.stderr)
    return 2
```

`eval_ship_check.py` is the exception — exit code carries the gate decision (0 = pass, 1 = fail) and there's no "known vs unexpected" axis; document this in its docstring.

---

### S3. Filesystem writes — mkdir + atomic-line append

**Source:** `apollo/model/train.py:save_checkpoint` (lines 169–180), `apollo/ingest/artifact.py:save_artifact` (lines 140–142), `apollo/scripts/train.py` lines 154–161 (CSV file open).

**Pattern:**
```python
out = Path(out_path)
out.parent.mkdir(parents=True, exist_ok=True)
with open(out, "a", encoding="utf-8") as f:
    f.write(json.dumps(record, separators=(",", ":")) + "\n")
    f.flush()
```

**Apply to:** `runs_log.py`, `scores_log.py`, `render_manifest.py`, anywhere Phase 4 writes a file.

**Critical** for `POST /score` (Pitfall 2): two writes inside ONE `open()`, ONE flush.

---

### S4. Path-traversal validation

**Source:** `apollo/ingest/pairs.py` lines 68–75 — the only existing example of user-supplied-path validation.

**Pattern:**
```python
resolved = entry.resolve()
try:
    resolved.relative_to(root_path)
except ValueError:
    raise IngestError(str(entry), "path traversal: symlink escapes corpus root")
```

**Apply to:** every Flask route that takes `<nnn>` as a path variable (`/audio/<nnn>/call.wav`, `/audio/<nnn>/response.wav`, `/pair/<nnn>`, `/reveal/<nnn>`). Validate `nnn` is in the `enumerate_heldout(pairs_root)` set; reject 404 otherwise. Do NOT construct paths from `<nnn>` before validation.

---

### S5. Timestamp format

**Source:** `apollo/scripts/train.py` line 150 (`strftime("%Y%m%dT%H%M%SZ")`) and the recommended `datetime.now(timezone.utc).isoformat(timespec="seconds")` in RESEARCH §"Write the run manifest".

**Apply to:**
- `runs.jsonl` `created` field — ISO form (`2026-05-21T14:32:18+00:00`)
- `scores.jsonl` `ts` field — ISO form
- Filenames (if any) — keep compact `%Y%m%dT%H%M%SZ` to match Phase-2/3 checkpoint naming

---

### S6. Test scaffolding

**Source:** `tests/test_split_determinism.py` lines 1–18, `tests/test_ingest_smoke.py` lines 1–24.

**Pattern every new test file follows:**
```python
"""Tests for <module> (<REQ-IDs>).

<paragraph stating what contract is being pinned.>
"""
from __future__ import annotations

import pytest
...

from apollo.eval.<...> import <...>
```

**Fixture style — copy from `tests/test_generate.py` lines 27–50** for any test that needs a checkpoint + pair:
```python
@pytest.fixture(scope="module")
def mock_ckpt(tmp_path_factory):
    root = tmp_path_factory.mktemp("eval_pairs")
    synthesize_pair(root, nnn="000")
    # ...
    return ckpt_path, root / "000"
```

`synthesize_pair` is already exported from `apollo.ingest` (`apollo/ingest/__init__.py` line 21) — reuse it for all Phase-4 fixtures that need real-looking pair folders.

---

### S7. Decision-ID and requirement traceability in docstrings

**Source:** Every existing module — e.g. `apollo/scripts/generate.py` lines 1–14, `apollo/scripts/train.py` lines 1–10, `apollo/ingest/split.py` lines 1–12.

**Pattern:** the first paragraph of every module docstring names the REQ-IDs it delivers and the D-numbers it implements:
```python
"""apollo/scripts/generate.py — autoregressive inference CLI.

INFER-01: Accepts checkpoint + call.mid + call.wav, emits response.mid.
INFER-02: --max-tokens flag.

Decisions:
- D-13: BPM read from call MIDI via pretty_midi.PrettyMIDI(path).estimate_tempo()
- D-14: defaults temperature=0.8, top-k=10
...
"""
```

**Apply to every Phase-4 file** — map EVAL-01..EVAL-05 + D-01..D-17 onto the modules that implement them. Planner should ensure each D-number from CONTEXT appears in exactly one module's docstring (no orphans, no duplicates).

---

## Files With No In-Repo Analog

These files have no close codebase match. Planner / executor should follow RESEARCH.md and UI-SPEC.md verbatim for these.

| File | Why No Analog | Fallback Reference |
|---|---|---|
| `apollo/eval/web/app.py` | First Flask app in the project | RESEARCH §Pattern 3 (full create_app() factory at lines 336–387) |
| `apollo/eval/web/templates/*.html` | No Jinja templates in repo | UI-SPEC §Layout + §Copywriting Contract |
| `apollo/eval/web/static/grade.js` | No JS in repo | UI-SPEC §Interaction Contract |
| `apollo/eval/web/static/style.css` | No CSS in repo | UI-SPEC §Color, §Typography, §Spacing |
| `eval/delta.ipynb` | First notebook in repo | RESEARCH §Delta Notebook Structure (6 cells, ≤5 lines each) |
| `eval/rubric.md` | First user-facing rubric doc | RESEARCH §Rubric Schema (CONTEXT D-01..D-03 anchors) |
| `m4l/ApolloRender.amxd` | First M4L device | RESEARCH §Pattern 4 (full `[sfrecord~]` + JS LiveAPI design + Pitfalls 1–7) |
| `m4l/ApolloRender.README.md` | First M4L docs | Document the manifest path contract (D-13, RESEARCH Open Q #3) |

---

## Metadata

**Analog search scope:** `apollo/ingest/**`, `apollo/scripts/**`, `apollo/model/train.py`, `tests/**`, `pyproject.toml`
**Files scanned:** ~25 source files + 17 test files (read directly: 9 files; full enumeration via `find` + `grep`)
**Existing patterns reused (no new conventions invented):**
- Module docstring + `from __future__ import annotations` + 3-block imports (S1)
- `def main(argv=None) -> int:` + `sys.exit(main())` CLI shape (S2)
- `mkdir(parents=True, exist_ok=True)` + atomic write (S3)
- `Path.resolve()` + `relative_to(root)` traversal guard (S4)
- ISO UTC timestamps (S5)
- `pytest` fixture + `tmp_path_factory` + `synthesize_pair` for test data (S6)
- REQ-ID + D-number traceability in every module docstring (S7)

**Pattern extraction date:** 2026-05-21
