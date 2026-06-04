"""Flask application factory for the Apollo local app (APP-01, APP-02).

Mirrors apollo/eval/web/app.py in structure and security conventions.

Routes (skeleton — extended by later Phase 5 plans):
  GET  /                          dashboard (3-tile home)
  GET  /audio/<nnn>/<filename>    serve call.wav for a known pair
  GET  /midi/<nnn>/<filename>     return note JSON for call.mid or response.mid
  GET  /status                    JSON snapshot of TrainingJob state

Security:
  T-05-01 (path traversal): _validate_pair_nnn rejects any <nnn> not in
    _known_pairs_set() with abort(404) BEFORE the nnn is used in a path.
    Filename is allow-listed (/midi: call.mid|response.mid, /audio: call.wav).
  T-05-02 (server binding): host is always 127.0.0.1 in __main__.py; debug=False.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request, send_file

from apollo.ingest.errors import IngestError
from apollo.ingest.midi import load_notes
from apollo.app.jobs import TrainingJob


def create_app(pairs_root: str = "data/pairs") -> Flask:
    """Create and configure the Apollo local app.

    Parameters
    ----------
    pairs_root:
        Path to the directory containing pair subdirectories (NNN/).
        Resolved to an absolute path — Flask send_file resolves relative paths
        against the app's root_path (apollo/app/), NOT cwd, so a relative
        pairs_root from the CLI would 500 every audio request.
    """
    app = Flask(__name__)

    # Always resolve to absolute path (PATTERNS.md §Flask create_app factory).
    app.config["PAIRS_ROOT"] = Path(pairs_root).resolve()
    app.config["TRAINING_JOB"] = TrainingJob()
    app.config["AUTO_RETRAIN"] = False
    app.config["RESPONSES_DIR"] = (Path.cwd() / "data" / "responses")

    # ------------------------------------------------------------------ helpers

    def _known_pairs_set() -> set[str]:
        """Enumerate pairs by call.mid + call_fm.json presence.

        NOTE: does NOT use discover_pairs — that helper requires call.wav which
        the app creates during /ingest (RESEARCH Pitfall 5). A pair directory is
        "known" the moment call.mid + call_fm.json are present, regardless of
        whether call.wav has been rendered yet.
        """
        root: Path = app.config["PAIRS_ROOT"]
        known: set[str] = set()
        if not root.is_dir():
            return known
        for child in root.iterdir():
            if not child.is_dir():
                continue
            if (child / "call.mid").is_file() and (child / "call_fm.json").is_file():
                known.add(child.name)
        return known

    def _validate_pair_nnn(nnn: str) -> Path:
        """Abort 404 if nnn is not a known pair; return its directory Path.

        T-05-01 mitigation: nnn is matched against the filesystem-enumerated
        known-pairs set and NEVER used to build a path before this validation.
        """
        if nnn not in _known_pairs_set():
            abort(404)
        return app.config["PAIRS_ROOT"] / nnn

    # ------------------------------------------------------------------ routes

    @app.get("/")
    def dashboard():
        known = _known_pairs_set()
        return render_template(
            "dashboard.html",
            n_pairs=len(known),
            pairs=sorted(known),
            target=30,
        )

    @app.get("/audio/<nnn>/<path:filename>")
    def pair_audio(nnn: str, filename: str):
        _validate_pair_nnn(nnn)
        if filename != "call.wav":
            abort(400)
        path = app.config["PAIRS_ROOT"] / nnn / "call.wav"
        if not path.is_file():
            abort(404)
        return send_file(path, mimetype="audio/wav")

    @app.get("/midi/<nnn>/<filename>")
    def midi_notes(nnn: str, filename: str):
        pair_path = _validate_pair_nnn(nnn)
        if filename not in ("call.mid", "response.mid"):
            abort(400)
        mid_path = pair_path / filename
        if not mid_path.is_file():
            abort(404)
        try:
            notes = load_notes(str(mid_path), str(pair_path), tempo_bpm=120.0)
        except IngestError as e:
            return jsonify({"ok": False, "error": e.reason}), 400
        return jsonify([
            {
                "pitch": n.pitch,
                "velocity": n.velocity,
                "start": n.start,
                "duration": n.end - n.start,
            }
            for n in notes
        ])

    @app.get("/status")
    def status():
        return jsonify(app.config["TRAINING_JOB"].snapshot())

    @app.get("/corpus")
    def corpus():
        """List all known pairs with their call_fm.json patch for audition.

        T-05-04 (path traversal): only iterates the filesystem-enumerated known
        pairs set — never accepts a user-supplied nnn for this route.
        T-05-05 (XSS): patch JSON is emitted via Jinja | tojson inside a
        <script type="application/json"> block; parsed client-side with JSON.parse.
        T-05-06 (malformed manifest): json.loads failure marks pair invalid without
        crashing; no patch tag is emitted for invalid pairs.
        """
        root: Path = app.config["PAIRS_ROOT"]
        pairs_out = []
        for nnn in sorted(_known_pairs_set()):
            fm_path = root / nnn / "call_fm.json"
            try:
                patch = json.loads(fm_path.read_text(encoding="utf-8"))
                valid = True
            except Exception:
                patch = None
                valid = False
            pairs_out.append({"nnn": nnn, "patch": patch, "valid": valid})
        return render_template(
            "corpus.html",
            pairs=pairs_out,
            n_pairs=len(pairs_out),
            target=30,
        )

    return app
