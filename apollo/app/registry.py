"""Append-only run registry for Apollo app (APP-14, APP-15).

This module is the *app layer* registry — it is written ONLY by the
Apollo Flask app (TrainingJob completion handler), never by train.py or
generate.py.  CLI-only training runs (`python -m apollo.scripts.train ...`)
will produce a checkpoint on disk but will NOT populate runs.jsonl in v1.
`_active_checkpoint()` in app.py falls back to mtime-latest, so those
checkpoints ARE usable by /generate; they simply won't appear in the /models
history view until a future enhancement teaches the CLI to log runs.

Registry format
---------------
models/runs.jsonl  — append-only, one JSON object per line.  Newest entry
                     is the LAST line (list_runs returns reversed).
models/ACTIVE      — plain-text file containing the BASENAME of the user's
                     chosen checkpoint.  Absent = "always use latest-by-mtime".

Reproducibility caveat (NOTE — do not implement here):
  corpus_hash is a CONTENT FLAG only — "this checkpoint was trained on a
  different corpus than you have on disk now".  It does NOT snapshot the corpus
  for full reproducibility.  Full corpus snapshotting is deferred to SEED-011.
"""
from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

# Module-level lock: serialises concurrent appends
# (auto-retrain timer + manual /train can race in the daemon thread).
_lock = threading.Lock()


# ------------------------------------------------------------------ helpers

def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------------ path helpers

def runs_path(models_dir) -> Path:
    """Return the Path to models/runs.jsonl."""
    return Path(models_dir) / "runs.jsonl"


def active_path(models_dir) -> Path:
    """Return the Path to models/ACTIVE."""
    return Path(models_dir) / "ACTIVE"


# ------------------------------------------------------------------ corpus hash

def compute_corpus_hash(pairs_root) -> str:
    """Compute a deterministic content hash over the corpus at call time.

    Algorithm (DOCUMENTED — do not change without updating the docstring):
    1. Enumerate pair dirs under ``pairs_root`` whose name is exactly 3 digits
       AND that contain both ``call.mid`` and ``call_fm.json``  (mirrors
       ``_known_pairs_set`` in app.py).
    2. Sort the dir names lexicographically.
    3. For each dir, feed the following into a running sha256 accumulator,
       in fixed order, IF the file exists:
         ``call.mid``      → "<name>:call.mid:<sha256(file_bytes)>"
         ``call_fm.json``  → "<name>:call_fm.json:<sha256(file_bytes)>"
         ``response.mid``  → "<name>:response.mid:<sha256(file_bytes)>"
       (Missing optional ``response.mid`` is simply skipped — its absence is
       part of the deterministic input.)
    4. Return h.hexdigest().

    An empty corpus returns the hexdigest of an empty sha256 input (stable).

    This is a CONTENT FLAG only (SEED-011 caveat: not a snapshot).
    """
    root = Path(pairs_root)
    h = hashlib.sha256()

    if not root.is_dir():
        return h.hexdigest()

    # Collect qualifying dirs
    pair_dirs = sorted(
        d.name
        for d in root.iterdir()
        if d.is_dir()
        and len(d.name) == 3
        and d.name.isdigit()
        and (d / "call.mid").is_file()
        and (d / "call_fm.json").is_file()
    )

    for name in pair_dirs:
        d = root / name
        for fname in ("call.mid", "call_fm.json", "response.mid"):
            fpath = d / fname
            if fpath.is_file():
                file_hash = hashlib.sha256(fpath.read_bytes()).hexdigest()
                h.update(f"{name}:{fname}:{file_hash}".encode())

    return h.hexdigest()


# ------------------------------------------------------------------ registry writes

def append_run(
    models_dir,
    *,
    checkpoint: str,
    iteration: int,
    corpus_pair_count: int,
    corpus_hash: str,
    held_loss: float | None,
    train_loss: float | None,
    timestamp: str | None = None,
) -> dict:
    """Append one completed-run row to models/runs.jsonl.

    The ``checkpoint`` argument may be an absolute path or a basename;
    only the basename (``Path(checkpoint).name``) is stored.

    Returns the row dict that was appended.

    NOTE: a new appended run does NOT move models/ACTIVE (pin-vs-retrain,
    D-06).  A pin survives subsequent auto/manual retrains until the user
    explicitly re-activates a checkpoint via /models/activate.
    """
    row = {
        "checkpoint": Path(checkpoint).name,
        "timestamp": timestamp or _utc_now(),
        "iteration": int(iteration),
        "corpus_pair_count": int(corpus_pair_count),
        "corpus_hash": corpus_hash,
        "held_loss": held_loss,
        "train_loss": train_loss,
    }

    path = runs_path(models_dir)
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")

    return row


# ------------------------------------------------------------------ registry reads

def list_runs(models_dir) -> list[dict]:
    """Return all recorded runs, newest-first.

    Tolerates corrupt / unparseable lines — those are silently skipped so
    the /models view never crashes on a partially-written line.
    If runs.jsonl does not exist, returns [].
    """
    path = runs_path(models_dir)
    if not path.is_file():
        return []

    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except (json.JSONDecodeError, ValueError):
            # Corrupt line — skip rather than crash the view.
            continue

    return list(reversed(rows))


# ------------------------------------------------------------------ ACTIVE pointer

def get_active(models_dir) -> str | None:
    """Return the stored checkpoint basename from models/ACTIVE, or None.

    Returns None if the ACTIVE file does not exist or is empty.
    """
    p = active_path(models_dir)
    if p.is_file():
        text = p.read_text(encoding="utf-8").strip()
        return text if text else None
    return None


def set_active(models_dir, checkpoint_basename: str) -> None:
    """Write ``checkpoint_basename`` to models/ACTIVE.

    CALLER MUST validate membership against list_runs() BEFORE calling this
    function (T-05-17 mitigation is in the /models/activate route, not here).
    Stored as basename with a trailing newline.
    """
    active_path(models_dir).write_text(checkpoint_basename.strip() + "\n", encoding="utf-8")


def clear_active(models_dir) -> None:
    """Remove models/ACTIVE, returning generation to latest-by-mtime mode."""
    p = active_path(models_dir)
    if p.exists():
        p.unlink()
