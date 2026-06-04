"""Flask application factory for the Apollo local app (APP-01..APP-03, APP-07, APP-08, APP-12).

Mirrors apollo/eval/web/app.py in structure and security conventions.

Routes:
  GET  /                          dashboard (3-tile home)
  GET  /corpus                    corpus drill-in (pair list + upload UI)
  GET  /training                  training view (progress bar + loss curve)
  GET  /generate                  generate view (patch editor + call→response flow)
  GET  /audio/<nnn>/<filename>    serve call.wav for a known pair
  GET  /midi/<nnn>/<filename>     return note JSON for call.mid or response*.mid
  GET  /status                    JSON snapshot of TrainingJob state
  POST /ingest                    upload call.mid + call_fm.json; write pair dir + render call.wav
  POST /train                     start training subprocess
  GET  /settings                  return current settings JSON
  POST /settings                  update responses_dir and/or auto_retrain
  GET  /presets                   list bundled preset names
  GET  /presets/<name>            return a bundled preset JSON (traversal-safe)
  POST /generate                  upload call.mid + call_fm; subprocess generate.py; copy response
  GET  /responses                 list files in RESPONSES_DIR

Security:
  T-05-01 (path traversal): _validate_pair_nnn rejects any <nnn> not in
    _known_pairs_set() with abort(404) BEFORE the nnn is used in a path.
    Filename is allow-listed (/midi: call.mid|response.mid|response_NNN.mid, /audio: call.wav).
  T-05-02 (server binding): host is always 127.0.0.1 in __main__.py; debug=False.
  T-05-07 (unsafe file write): pair dir allocated server-side via _allocate_next_nnn;
    no client-controlled path reaches the filesystem.
  T-05-08 (injection): manifest validated via load_manifest + load_notes before write;
    partial dir removed on failure.
  T-05-09 (command injection): TrainingJob.start builds argv from fixed list; no
    user string concatenated; no shell=True.
  T-05-12 (path traversal): /presets/<name> allow-listed to [a-z_]+ only.
  T-05-13 (manifest injection): /generate validates call_fm via load_manifest before
    any write or subprocess.
  T-05-14 (command injection): /generate subprocess uses a fixed argv list; no shell=True;
    no user string in argv.
  T-05-15 (path traversal): /midi response filename matched against anchored regex.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
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
from apollo.app import registry

# Anchored regex for response filenames (T-05-15: traversal-safe, no user string in path).
_RESPONSE_FILENAME_RE = re.compile(r'^response_\d+\.mid$')


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

    def _launch_training() -> bool:
        """Start training with a registry completion hook.

        corpus_hash and pair_count are snapshotted at launch time (before any
        new pair can land — D-06 race-safety). The on_complete closure captures
        them so the registry row reflects the corpus state at job start.

        NOTE: appending a run does NOT touch models/ACTIVE (pin-vs-retrain,
        D-06). A new run only becomes active if the user is on latest (ACTIVE
        unset) or explicitly activates it via /models/activate. We never
        auto-move an existing pin.
        """
        models_dir = "models"
        corpus_hash = registry.compute_corpus_hash(app.config["PAIRS_ROOT"])
        pair_count = len(_known_pairs_set())

        def _on_complete(train_loss, held_loss):
            ckpt = _latest_checkpoint()   # newest .pt by mtime == the run just produced
            if ckpt is None:
                return
            registry.append_run(
                models_dir,
                checkpoint=ckpt.name,
                iteration=1,              # train.py default iteration (CLI flag not set by app)
                corpus_pair_count=pair_count,
                corpus_hash=corpus_hash,
                held_loss=held_loss,
                train_loss=train_loss,
            )
            # NOTE: pin-vs-retrain (D-06) — appending a run does NOT touch ACTIVE.
            # A new run only becomes active if the user is on latest (ACTIVE unset)
            # or explicitly activates it (POST /models/activate). We never
            # auto-move an existing pin.

        return app.config["TRAINING_JOB"].start(
            str(app.config["PAIRS_ROOT"]), 300, models_dir, on_complete=_on_complete
        )

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
        # T-05-15: filename must be call.mid, response.mid, or response_NNN.mid
        # (anchored regex — no traversal possible).
        if filename not in ("call.mid", "response.mid") and not _RESPONSE_FILENAME_RE.match(filename):
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
        # _launch_training() snapshots corpus_hash + pair_count at timer fire
        # time (the moment the debounce fires, all uploads in the batch are
        # already on disk — D-06 race-safety).
        if app.config["AUTO_RETRAIN"]:
            if _debounce["timer"] is not None:
                _debounce["timer"].cancel()

            t = threading.Timer(3.0, _launch_training)
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
        Uses _launch_training() to snapshot corpus_hash + pair_count at launch
        and wire the registry on_complete callback (APP-14).
        """
        started = _launch_training()
        if not started:
            return jsonify({"ok": False, "error": "Training already running"}), 409
        return jsonify({"ok": True})

    # ---------------------------------------------------------------------- /generate page

    @app.get("/generate")
    def generate_page():
        """Generate view: MIDI upload + patch editor + call→response flow."""
        return render_template("generate.html")

    # ---------------------------------------------------------------------- /presets

    # T-05-12: name is allow-listed to [a-z_]+ only (charset check prevents traversal).
    _PRESET_NAME_RE = re.compile(r'^[a-z_]+$')
    _PRESETS_DIR = Path(__file__).parent / "presets"

    @app.get("/presets")
    def presets_list():
        """List bundled preset names (stem only, no extension)."""
        names = sorted(p.stem for p in _PRESETS_DIR.glob("*.json"))
        return jsonify(names)

    @app.get("/presets/<name>")
    def presets_get(name: str):
        """Return a bundled preset JSON file (traversal-safe).

        T-05-12: name is allow-listed to [a-z_]+; path is built under the
        package presets/ dir; file existence is checked.
        """
        if not _PRESET_NAME_RE.match(name):
            abort(400)
        path = _PRESETS_DIR / (name + ".json")
        if not path.is_file():
            abort(404)
        return send_file(str(path), mimetype="application/json")

    # ---------------------------------------------------------------------- /generate (POST)

    def _latest_checkpoint() -> Path | None:
        """Return the most-recently-modified .pt under models/, or None.

        RESEARCH OQ2: checkpoint selection by max mtime — uses the most recent
        checkpoint without requiring a manifest file.
        """
        candidates = list(Path("models").glob("*.pt")) if Path("models").is_dir() else []
        if not candidates:
            return None
        return max(candidates, key=lambda p: p.stat().st_mtime)

    @app.post("/generate")
    def generate():
        """Upload call.mid + call_fm (authored patch); subprocess generate.py; copy response.

        Security:
          T-05-13: load_manifest validates call_fm before any write or subprocess.
          T-05-14: fixed argv list; no shell=True; no user string in argv.

        Flow:
          1. Validate manifest (load_manifest on temp → IngestError → 400).
          2. Allocate pair dir; write call.mid + call_fm.json.
          3. Resolve latest checkpoint (None → 400 + rmtree).
          4. subprocess generate.py with FIXED argv (server-resolved paths).
          5. Find newest response_*.mid in pair dir; copy to RESPONSES_DIR.
          6. Return {ok, nnn, response, checkpoint}.
        """
        call_mid = request.files.get("call_mid")
        call_fm = request.files.get("call_fm")

        if call_mid is None or call_fm is None:
            return jsonify({"ok": False, "error": "call.mid and call_fm are both required"}), 400

        fm_bytes = call_fm.read()
        mid_bytes = call_mid.read()

        # 1. Validate manifest BEFORE allocating a dir (T-05-13).
        tmp_fm = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        try:
            tmp_fm.write(fm_bytes)
            tmp_fm.flush()
            tmp_fm.close()
            try:
                load_manifest(tmp_fm.name, "(generate-upload)")
            except IngestError as e:
                return jsonify({"ok": False, "error": e.reason}), 400
        finally:
            Path(tmp_fm.name).unlink(missing_ok=True)

        # 2. Allocate pair dir.
        pair = _allocate_next_nnn()
        try:
            (pair / "call_fm.json").write_bytes(fm_bytes)
            (pair / "call.mid").write_bytes(mid_bytes)

            # 3. Resolve checkpoint.
            ckpt = _latest_checkpoint()
            if ckpt is None:
                shutil.rmtree(pair)
                return jsonify({
                    "ok": False,
                    "error": "No trained model yet. Add a few pairs and train first, then generate.",
                }), 400

            # 4. Fixed argv list — NO shell=True, NO user string in argv (T-05-14).
            argv = [
                "python", "-m", "apollo.scripts.generate",
                str(ckpt.resolve()),
                str((pair / "call.mid").resolve()),
            ]
            result = subprocess.run(argv, capture_output=True, text=True)
            if result.returncode != 0:
                shutil.rmtree(pair)
                err_msg = result.stderr[-500:] if result.stderr else "generation failed"
                return jsonify({"ok": False, "error": err_msg}), 500

            # 5. Find newest response_*.mid in the pair dir.
            response_files = sorted(pair.glob("response_*.mid"), key=lambda f: f.stat().st_mtime)
            if not response_files:
                shutil.rmtree(pair)
                return jsonify({"ok": False, "error": "generate.py produced no response file"}), 500

            newest_response = response_files[-1]
            responses_dir: Path = app.config["RESPONSES_DIR"]
            responses_dir.mkdir(parents=True, exist_ok=True)
            copied_name = f"{pair.name}_{newest_response.name}"
            shutil.copy2(str(newest_response), str(responses_dir / copied_name))

        except Exception:
            if pair.exists():
                shutil.rmtree(pair)
            raise

        return jsonify({
            "ok": True,
            "nnn": pair.name,
            "response": copied_name,
            "checkpoint": str(ckpt),
        })

    # ---------------------------------------------------------------------- /responses

    @app.get("/responses")
    def responses_list():
        """List files in RESPONSES_DIR (D-12 configurable store)."""
        responses_dir: Path = app.config["RESPONSES_DIR"]
        if not responses_dir.is_dir():
            return jsonify({"ok": True, "responses": []})
        names = sorted(f.name for f in responses_dir.iterdir() if f.is_file())
        return jsonify({"ok": True, "responses": names})

    return app
