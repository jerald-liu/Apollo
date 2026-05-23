"""Apollo eval package — held-out enumeration, run identity, score store, ship gate.

Public surface (filled in as Phase 4 plans land; placeholder during Wave 1):
    - compute_run_id        (apollo/eval/run_id.py)
    - enumerate_heldout     (apollo/eval/heldout.py)
    - append_run            (apollo/eval/runs_log.py)
    - append_score, append_score_pair, load_scores  (apollo/eval/scores_log.py)
    - check_ship_gate       (apollo/eval/ship_check.py)
    - write_render_manifest (apollo/eval/render_manifest.py)

Scaffolded by 04-01-PLAN. Re-exports are added by 04-02-PLAN once modules exist.

See .planning/phases/04-evaluation-loop/04-CONTEXT.md (D-01..D-17) and
.planning/phases/04-evaluation-loop/04-RESEARCH.md.
"""
from __future__ import annotations

__all__: list[str] = []
