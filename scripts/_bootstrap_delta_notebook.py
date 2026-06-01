"""One-shot generator for eval/delta.ipynb.

Run with: `python scripts/_bootstrap_delta_notebook.py`
Idempotent — re-running overwrites the notebook with the canonical 5-cell layout.

Cells (RESEARCH §Delta Notebook Structure):
  1. Imports + paths
  2. Load + dedup to latest-per-key
  3. Plot 1 — per-dim mean over runs (REQUIRED, EVAL-04)
  4. Plot 2 — per-pair fit trajectories (REQUIRED, EVAL-04)
  5. Ship-gate explainer cell

A 6th optional cell ("bottom-N regressed pairs") is NOT included to keep
the notebook lean — user can add it ad-hoc; canonical cells stay pinned.
"""
from __future__ import annotations

from pathlib import Path

import nbformat as nbf

nb = nbf.v4.new_notebook()

cells = []

cells.append(nbf.v4.new_markdown_cell(
    "# Apollo Eval — Delta Notebook (EVAL-04, D-10)\n\n"
    "Reads `eval/scores.jsonl` + `eval/runs.jsonl`, surfaces per-iteration deltas.\n\n"
    "**Restart Kernel and Run All when you grade new sessions** (Jupyter cells cache).\n\n"
    "Cells 1–5 are the canonical layout — do not delete. Add exploratory cells below cell 5."
))

cells.append(nbf.v4.new_code_cell(
    "import pandas as pd, matplotlib.pyplot as plt\n"
    "from pathlib import Path\n"
    "SCORES = Path('eval/scores.jsonl')\n"
    "RUNS = Path('eval/runs.jsonl')"
))

cells.append(nbf.v4.new_code_cell(
    "scores = pd.read_json(SCORES, lines=True)\n"
    "runs = pd.read_json(RUNS, lines=True)\n"
    "# Last-write-wins per (run_id, pair_id, dim) — RESEARCH Pattern 1.\n"
    "scores = scores.drop_duplicates(subset=['run_id','pair_id','dim'], keep='last')\n"
    "print(f'{len(runs)} runs · {len(scores)} score records · '\n"
    "      f\"{runs['iteration'].sum() if 'iteration' in runs else 0} iteration-marked\")"
))

cells.append(nbf.v4.new_code_cell(
    "# Plot 1 — Per-dim mean over runs (REQUIRED, EVAL-04 D-10)\n"
    "means = scores.groupby(['run_id','dim'])['score'].mean().unstack()\n"
    "means = means.reindex(runs.sort_values('created')['run_id'])\n"
    "ax = means.plot(marker='o', figsize=(8,4))\n"
    "ax.set_xticklabels([r[:8] for r in means.index], rotation=45)\n"
    "ax.set_title('Mean score per dimension across runs')\n"
    "ax.set_ylabel('mean score (1–5)')\n"
    "plt.tight_layout(); plt.show()"
))

cells.append(nbf.v4.new_code_cell(
    "# Plot 2 — Per-pair call-response-fit trajectories (REQUIRED, EVAL-04 D-10)\n"
    "fit = scores[scores.dim == 'fit']\n"
    "pivot = fit.pivot_table(index='run_id', columns='pair_id', values='score')\n"
    "pivot = pivot.reindex(runs.sort_values('created')['run_id'])\n"
    "ax = pivot.plot(figsize=(10,5), legend=False, alpha=0.5)\n"
    "ax.set_xticklabels([r[:8] for r in pivot.index], rotation=45)\n"
    "ax.set_title('Per-pair fit trajectory'); ax.set_ylabel('fit score (1–5)')\n"
    "plt.tight_layout(); plt.show()"
))

cells.append(nbf.v4.new_code_cell(
    "# Ship-gate (EVAL-05) — same logic as `python -m apollo.scripts.eval_ship_check`\n"
    "from apollo.eval import check_ship_gate\n"
    "passed, banner = check_ship_gate()\n"
    "print(banner)\n"
    "print('\\n→', 'SHIP-READY' if passed else 'NOT YET — keep iterating')"
))

nb['cells'] = cells

out = Path('eval/delta.ipynb')
out.parent.mkdir(parents=True, exist_ok=True)
nbf.write(nb, str(out))
print(f'wrote {out}')
