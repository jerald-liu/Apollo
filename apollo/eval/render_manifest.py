"""Write the per-run render manifest the M4L device consumes.

Decisions:
- D-13: M4L coordinates via folder convention. The manifest at
        `eval/render_manifests/active.json` is the single source of truth
        (RESEARCH Open Q #3 — hardcoded path; apollo eval render overwrites).
- A1   (RESEARCH): one entry per held-out pair, always `response_001.mid`.
        N-sample grading (--n > 1 in generate.py) is a v2 feature; later
        samples are NOT entered in the manifest.

Pairs missing `response_001.mid` are SKIPPED with a stderr warning so the
user knows to re-run `generate.py` for those pairs.

JSON sidecar: each entry includes a `notes_json` path that the M4L device
reads instead of parsing MIDI in JS (RESEARCH §Pattern 4 Pitfall 1). Writing
the sidecar itself is the M4L preprocessing step's job — this manifest just
declares the expected path.

See .planning/phases/04-evaluation-loop/04-RESEARCH.md §"render_manifest"
and §Pattern 4.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List

from apollo.eval.heldout import enumerate_heldout

DEFAULT_MANIFEST_PATH = "eval/render_manifests/active.json"


def write_render_manifest(
    run_id: str,
    pairs_root: str,
    manifest_path: str = DEFAULT_MANIFEST_PATH,
) -> Path:
    """Write `{run_id, entries[]}` to `manifest_path` and return the Path.

    Entries:
        {nnn, response_mid, out_wav, notes_json}

    Skipped held-out pairs (no response_001.mid yet) print a warning to stderr.
    """
    heldout = enumerate_heldout(pairs_root)
    entries: List[dict] = []
    for pp in heldout:
        response_mid = pp.dir / "response_001.mid"
        if not response_mid.is_file():
            print(
                f"WARNING: pair {pp.nnn} has no response_001.mid; skipping "
                f"(re-run generate.py for this pair).",
                file=sys.stderr,
            )
            continue
        out_wav = pp.dir / "eval" / run_id / "response.wav"
        notes_json = response_mid.with_suffix(".notes.json")
        entries.append({
            "nnn": pp.nnn,
            "response_mid": str(response_mid),
            "out_wav": str(out_wav),
            "notes_json": str(notes_json),
        })
    out = Path(manifest_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"run_id": run_id, "entries": entries}, indent=2))
    return out
