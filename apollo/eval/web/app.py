"""Flask grading UI for held-out scoring (EVAL-02, D-04..D-07).

Five user-facing routes + one pre-population helper:
  GET  /                  — worklist (UI-SPEC §Layout)
  GET  /pair/<nnn>        — score one pair
  GET  /audio/<nnn>/call.wav     — serve pair audio
  GET  /audio/<nnn>/response.wav — serve per-run rendered audio
  POST /score             — append fit+coherence atomically (Pitfall 2)
  GET  /reveal/<nnn>      — blind-mode reveal (D-05)
  GET  /score/<nnn>       — pre-population for resumed pair-page (UI-SPEC §Resumability)

Decisions:
- D-05: blind by default — run_id_short shown only in page title slot, never on
        individual pair pages or in the DOM of /pair/<nnn>.
- D-07: response.wav is pre-rendered; this app does not touch Ableton.
- D-13: per-pair audio under data/pairs/NNN/eval/<run_id>/response.wav.

Path-traversal: every <nnn> route variable is validated against
enumerate_heldout(pairs_root) set membership BEFORE constructing a Path
(PATTERNS S4, RESEARCH Pitfall 5).
"""
from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from typing import List

from flask import (
    Flask, abort, jsonify, render_template, request, send_file, url_for,
)

from apollo.eval.heldout import enumerate_heldout
from apollo.eval.scores_log import append_score_pair, load_scores


def _shuffled_pair_nnns(pairs_root: str, run_id: str) -> List[str]:
    """Deterministic shuffle per run (UI-SPEC §Blind Grading).

    Seeded via blake2b rather than built-in hash() — string hash() is salted
    per-process by PYTHONHASHSEED, so a built-in seed would re-shuffle the
    worklist on every restart and undermine resumability.
    """
    nnns = [p.nnn for p in enumerate_heldout(pairs_root)]
    seed = int.from_bytes(hashlib.blake2b(run_id.encode(), digest_size=8).digest(), "big")
    rng = random.Random(seed)
    rng.shuffle(nnns)
    return nnns


def _graded_pair_ids(run_id: str, scores_path: str) -> set[str]:
    recs = load_scores(run_id=run_id, path=scores_path)
    # latest-write-wins per (pair_id, dim)
    latest: dict[tuple[str, str], dict] = {}
    for r in recs:
        latest[(r["pair_id"], r["dim"])] = r
    # graded == has both fit AND coherence for that pair_id
    pairs = {pid for (pid, _dim) in latest.keys()}
    return {pid for pid in pairs
            if (pid, "fit") in latest and (pid, "coherence") in latest}


def _find_run_record(run_id: str, runs_path: str) -> dict | None:
    p = Path(runs_path)
    if not p.is_file():
        return None
    last = None
    with open(p, encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as exc:
                # A single corrupt line (e.g. partial write after kill -9)
                # should not take down the grading session — skip and warn.
                import sys
                print(f"WARN: skipping malformed {runs_path}:{lineno} — {exc}",
                      file=sys.stderr)
                continue
            if rec.get("run_id") == run_id:
                last = rec
    return last


def create_app(
    pairs_root: str,
    run_id: str,
    eval_root: str = "eval",
    runs_path: str = "eval/runs.jsonl",
    scores_path: str = "eval/scores.jsonl",
) -> Flask:
    app = Flask(__name__)
    # Resolve PAIRS_ROOT to an absolute path — Flask's send_file resolves
    # relative paths against the app's root_path (apollo/eval/web/), NOT cwd,
    # so a relative pairs_root from the CLI would 500 every audio request.
    app.config["PAIRS_ROOT"] = Path(pairs_root).resolve()
    app.config["RUN_ID"] = run_id
    app.config["EVAL_ROOT"] = Path(eval_root)
    app.config["RUNS_PATH"] = runs_path
    app.config["SCORES_PATH"] = scores_path

    def _heldout_set() -> set[str]:
        return {p.nnn for p in enumerate_heldout(str(app.config["PAIRS_ROOT"]))}

    def _validate_nnn(nnn: str) -> None:
        if nnn not in _heldout_set():
            abort(404)

    @app.get("/")
    def index():
        nnns = _shuffled_pair_nnns(str(app.config["PAIRS_ROOT"]), run_id)
        graded = _graded_pair_ids(run_id, app.config["SCORES_PATH"])
        unrenderable = set()
        for nnn in nnns:
            wav = (app.config["PAIRS_ROOT"] / nnn / "eval" / run_id / "response.wav")
            if not wav.is_file():
                unrenderable.add(nnn)
        return render_template(
            "index.html",
            pairs=nnns,
            graded=graded,
            unrenderable=unrenderable,
            run_id_short=run_id[:8],
            n_total=len(nnns),
            n_graded=len(graded),
            n_remaining=len(nnns) - len(graded),
        )

    @app.get("/pair/<nnn>")
    def pair_view(nnn):
        _validate_nnn(nnn)
        shuffled = _shuffled_pair_nnns(str(app.config["PAIRS_ROOT"]), run_id)
        position = shuffled.index(nnn) + 1
        return render_template(
            "pair.html",
            nnn=nnn,
            position=position,
            total=len(shuffled),
        )

    @app.get("/audio/<nnn>/call.wav")
    def call_audio(nnn):
        _validate_nnn(nnn)
        path = app.config["PAIRS_ROOT"] / nnn / "call.wav"
        if not path.is_file():
            abort(404)
        return send_file(path, mimetype="audio/wav")

    @app.get("/audio/<nnn>/response.wav")
    def response_audio(nnn):
        _validate_nnn(nnn)
        path = (
            app.config["PAIRS_ROOT"] / nnn / "eval" / run_id / "response.wav"
        )
        if not path.is_file():
            abort(404)
        return send_file(path, mimetype="audio/wav")

    @app.post("/score")
    def submit_score():
        data = request.get_json(silent=True) or {}
        try:
            pair_id = str(data["pair_id"])
            fit = int(data["fit"])
            coherence = int(data["coherence"])
            note = str(data.get("note", ""))
        except (KeyError, TypeError, ValueError):
            return jsonify({"ok": False, "error": "bad payload"}), 400
        if pair_id not in _heldout_set():
            return jsonify({"ok": False, "error": "unknown pair"}), 404
        if not (1 <= fit <= 5 and 1 <= coherence <= 5):
            return jsonify({"ok": False, "error": "scores must be 1..5"}), 400
        append_score_pair(
            run_id, pair_id, fit=fit, coherence=coherence, note=note,
            path=app.config["SCORES_PATH"],
        )
        # Next pending pair in shuffled order, for the client's auto-advance.
        # Single-grader assumption: there is no lock between the append above
        # and the re-read below. Concurrent writers would race the "next
        # pending" computation. v1 Apollo is a single-user local tool; revisit
        # if grading ever goes multi-user (WR-04).
        shuffled = _shuffled_pair_nnns(str(app.config["PAIRS_ROOT"]), run_id)
        graded = _graded_pair_ids(run_id, app.config["SCORES_PATH"])
        next_nnn = next((n for n in shuffled if n not in graded), None)
        return jsonify({"ok": True, "next": next_nnn})

    @app.get("/reveal/<nnn>")
    def reveal(nnn):
        _validate_nnn(nnn)
        rec = _find_run_record(run_id, app.config["RUNS_PATH"]) or {}
        return jsonify({
            "run_id": run_id,
            "checkpoint_path": rec.get("checkpoint_path"),
            "iteration": rec.get("iteration"),
        })

    @app.get("/score/<nnn>")
    def latest_score(nnn):
        _validate_nnn(nnn)
        recs = load_scores(run_id=run_id, path=app.config["SCORES_PATH"])
        latest = {"fit": None, "coherence": None, "note": ""}
        for r in recs:
            if r["pair_id"] != nnn:
                continue
            if r["dim"] == "fit":
                latest["fit"] = r["score"]
                if r.get("note"):
                    latest["note"] = r["note"]
            elif r["dim"] == "coherence":
                latest["coherence"] = r["score"]
        return jsonify(latest)

    return app
