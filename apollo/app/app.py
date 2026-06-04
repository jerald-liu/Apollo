"""Flask application factory for the Apollo local app (APP-01..APP-03, APP-07, APP-08, APP-12).

Mirrors apollo/eval/web/app.py in structure and security conventions.

Routes:
  GET  /                          dashboard (3-tile home)
  GET  /corpus                    corpus drill-in (pair list + upload UI)
  GET  /training                  training view (progress bar + loss curve)
  GET  /audio/<nnn>/<filename>    serve call.wav for a known pair
  GET  /midi/<nnn>/<filename>     return note JSON for call.mid or response.mid
  GET  /status                    JSON snapshot of TrainingJob state
  POST /ingest                    upload call.mid + call_fm.json; write pair dir + render call.wav
  POST /train                     start training subprocess
  GET  /settings                  return current settings JSON
  POST /settings                  update responses_dir and/or auto_retrain

Security:
  T-05-01 (path traversal): _validate_pair_nnn rejects any <nnn> not in
    _known_pairs_set() with abort(404) BEFORE the nnn is used in a path.
    Filename is allow-listed (/midi: call.mid|response.mid, /audio: call.wav).
  T-05-02 (server binding): host is always 127.0.0.1 in __main__.py; debug=False.
  T-05-07 (unsafe file write): pair dir allocated server-side via _allocate_next_nnn;
    no client-controlled path reaches the filesystem.
  T-05-08 (injection): manifest validated via load_manifest + load_notes before write;
    partial dir removed on failure.
  T-05-09 (command injection): TrainingJob.start builds argv from fixed list; no
    user string concatenated; no shell=True.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import threading
from pathlib import Path

import soundfile as sf
from flask import Flask, abort, jsonify, render_template, request, send_file

from apollo.ingest.errors import IngestError
from apollo.ingest.midi import load_notes
from apollo.synth.manifest import load_manifest
from apollo.synth.render import render
from apollo.synth.spec import SR
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

    # Module-level locks/debounce state — scoped inside factory closure.
    _alloc_lock = threading.Lock()
    _debounce: dict = {"timer": None}

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

    def _allocate_next_nnn() -> Path:
        """Allocate the next sequential NNN directory under PAIRS_ROOT.

        T-05-07 mitigation: the pair directory path is server-allocated; the
        client never supplies a path.  The lock prevents a concurrent-upload
        race (RESEARCH OQ4).
        """
        root: Path = app.config["PAIRS_ROOT"]
        root.mkdir(parents=True, exist_ok=True)
        with _alloc_lock:
            existing = [
                int(d.name)
                for d in root.iterdir()
                if d.is_dir() and d.name.isdigit() and len(d.name) == 3
            ]
            nxt = (max(existing, default=-1) + 1)
            pair_dir = root / f"{nxt:03d}"
            pair_dir.mkdir(parents=True)
        return pair_dir

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

    @app.post("/ingest")
    def ingest():
        """Upload call.mid + call_fm.json; validate, write pair dir, render call.wav.

        Security:
          T-05-07: pair dir allocated server-side (_allocate_next_nnn).
          T-05-08: validate via load_manifest + load_notes; remove partial dir on failure.
        """
        call_mid = request.files.get("call_mid")
        call_fm = request.files.get("call_fm")
        response_mid = request.files.get("response_mid")

        if call_mid is None or call_fm is None:
            return jsonify({"ok": False, "error": "call.mid and call_fm.json are both required"}), 400

        fm_bytes = call_fm.read()
        mid_bytes = call_mid.read()

        # --- Validate manifest BEFORE allocating a dir (T-05-08).
        tmp_fm = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        try:
            tmp_fm.write(fm_bytes)
            tmp_fm.flush()
            tmp_fm.close()
            try:
                params = load_manifest(tmp_fm.name, "(upload)")
            except IngestError as e:
                return jsonify({"ok": False, "error": e.reason}), 400
        finally:
            Path(tmp_fm.name).unlink(missing_ok=True)

        # --- Allocate the pair directory (lock-guarded, T-05-07).
        pair = _allocate_next_nnn()

        try:
            # Write files to the allocated directory.
            (pair / "call_fm.json").write_bytes(fm_bytes)
            (pair / "call.mid").write_bytes(mid_bytes)

            # --- Validate + parse MIDI.
            try:
                notes = load_notes(str(pair / "call.mid"), str(pair))
            except IngestError as e:
                shutil.rmtree(pair)
                return jsonify({"ok": False, "error": e.reason}), 400

            # --- Render canonical call.wav IN-PROCESS (D-11/D-14, Pattern 3).
            try:
                audio = render(params, notes, pair_path=str(pair))
                sf.write(str(pair / "call.wav"), audio, SR)
            except IngestError as e:
                shutil.rmtree(pair)
                return jsonify({"ok": False, "error": e.reason}), 400

            # --- Optional response MIDI.
            if response_mid:
                (pair / "response.mid").write_bytes(response_mid.read())

        except Exception:
            # Unexpected error: clean up partial dir so no orphan remains.
            if pair.exists():
                shutil.rmtree(pair)
            raise

        # --- Debounced auto-retrain (D-06, one run per bulk drag-in).
        if app.config["AUTO_RETRAIN"]:
            if _debounce["timer"] is not None:
                _debounce["timer"].cancel()

            def _fire_retrain():
                app.config["TRAINING_JOB"].start(
                    str(app.config["PAIRS_ROOT"]), 300, "models"
                )

            t = threading.Timer(3.0, _fire_retrain)
            t.daemon = True
            t.start()
            _debounce["timer"] = t

        return jsonify({"ok": True, "nnn": pair.name})

    @app.get("/settings")
    def settings_get():
        """Return current configurable settings."""
        return jsonify({
            "ok": True,
            "responses_dir": str(app.config["RESPONSES_DIR"]),
            "auto_retrain": app.config["AUTO_RETRAIN"],
        })

    @app.post("/settings")
    def settings_post():
        """Update configurable settings (responses_dir, auto_retrain)."""
        data = request.get_json(silent=True) or {}
        if "responses_dir" in data:
            app.config["RESPONSES_DIR"] = Path(data["responses_dir"]).resolve()
        if "auto_retrain" in data:
            app.config["AUTO_RETRAIN"] = bool(data["auto_retrain"])
        return jsonify({
            "ok": True,
            "responses_dir": str(app.config["RESPONSES_DIR"]),
            "auto_retrain": app.config["AUTO_RETRAIN"],
        })

    @app.get("/training")
    def training():
        """Training view: progress bar + loss curve canvas + settings."""
        return render_template(
            "training.html",
            responses_dir=str(app.config["RESPONSES_DIR"]),
            auto_retrain=app.config["AUTO_RETRAIN"],
        )

    @app.post("/train")
    def train():
        """Start a background training job (D-02, D-03, D-05).

        Returns 409 if already running (one job at a time).
        """
        started = app.config["TRAINING_JOB"].start(
            str(app.config["PAIRS_ROOT"]), 300, "models"
        )
        if not started:
            return jsonify({"ok": False, "error": "Training already running"}), 409
        return jsonify({"ok": True})

    return app
