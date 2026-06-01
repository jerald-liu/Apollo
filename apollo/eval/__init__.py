"""Apollo eval package — held-out enumeration, run identity, score store, ship gate.

Public surface:
    - enumerate_heldout        (heldout.py)
    - compute_run_id           (run_id.py)
    - append_run               (runs_log.py)
    - append_score, append_score_pair, load_scores  (scores_log.py)
    - check_ship_gate          (ship_check.py)
    - write_render_manifest    (render_manifest.py)

See .planning/phases/04-evaluation-loop/04-CONTEXT.md (D-01..D-17) and
.planning/phases/04-evaluation-loop/04-RESEARCH.md.
"""
from __future__ import annotations

from .heldout import enumerate_heldout
from .render_manifest import write_render_manifest, DEFAULT_MANIFEST_PATH
from .run_id import compute_run_id
from .runs_log import append_run
from .scores_log import append_score, append_score_pair, load_scores
from .ship_check import check_ship_gate

__all__ = [
    "enumerate_heldout",
    "compute_run_id",
    "append_run",
    "append_score",
    "append_score_pair",
    "load_scores",
    "check_ship_gate",
    "write_render_manifest",
    "DEFAULT_MANIFEST_PATH",
]
