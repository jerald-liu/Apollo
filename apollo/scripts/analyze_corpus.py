"""apollo/scripts/analyze_corpus.py — corpus relationship analysis (off-model).

Not part of the training pipeline. A standalone lens over `data/pairs/` that
buckets each call and response into rhythmic/timbral archetypes and reports
call -> response co-occurrence matrices, surfacing corpus coverage gaps for
authoring.

This treats "call -> response" as edges in a small relationship graph:
  - nodes   = archetype buckets (e.g. call density: sparse/medium/dense)
  - edges   = authored pairs, grouped by (call archetype, response archetype)
  - weight  = how many pairs fall in that cell

Two matrices are reported:
  - density complement:     call note-density tertile  x  response note-density tertile
  - articulation complement: call duration/IOI tertile  x  response duration/IOI tertile

Plus two single-axis distributions (no response-side timbre exists, so
brightness is call-only; contour is response-only since it characterizes
the "answer shape"):
  - call brightness (mel spectral centroid): dark / mid / bright
  - response contour: ascending / descending / static

Usage:
    python -m apollo.scripts.analyze_corpus <pairs_root> [--tempo-bpm BPM] [--output PATH.json]

Exit codes (mirrors apollo.scripts.ingest_corpus):
    0 — Success (including the "no pairs yet" case).
    1 — IngestError: a known per-pair failure with the offending pair path.
    2 — Any other exception (bug / environment issue).
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import List

import numpy as np
import torch

from apollo.ingest import IngestError, MelExtractor, discover_pairs, load_notes
from apollo.tokenizer.types import Note

DENSITY_LABELS = ("sparse", "medium", "dense")
ARTICULATION_LABELS = ("staccato", "balanced", "legato")
BRIGHTNESS_LABELS = ("dark", "mid", "bright")


def _rhythmic_features(notes: List[Note]) -> dict:
    """Density, articulation (duration/IOI ratio), and pitch contour.

    `density` = notes per second over the phrase span.
    `duration_ratio` = mean note duration / mean inter-onset interval.
        Low (<1) -> staccato (gaps between notes); ~1 -> legato/connected;
        a single note has no IOI, so duration_ratio defaults to 1.0 (legato).
    `contour` = direction from first to last pitch.
    """
    starts = [n.start for n in notes]
    ends = [n.end for n in notes]
    durations = [n.end - n.start for n in notes]

    span = max(ends) - min(starts)
    density = (len(notes) / span) if span > 0 else float(len(notes))

    if len(notes) > 1:
        iois = [starts[i + 1] - starts[i] for i in range(len(notes) - 1)]
        mean_ioi = sum(iois) / len(iois)
    else:
        mean_ioi = 0.0

    mean_dur = sum(durations) / len(durations)
    duration_ratio = (mean_dur / mean_ioi) if mean_ioi > 0 else 1.0

    delta = notes[-1].pitch - notes[0].pitch
    if delta > 0:
        contour = "ascending"
    elif delta < 0:
        contour = "descending"
    else:
        contour = "static"

    return {
        "n_notes": len(notes),
        "density": density,
        "duration_ratio": duration_ratio,
        "contour": contour,
    }


def _timbral_features(log_mel: torch.Tensor) -> dict:
    """Brightness (spectral centroid) from the call's log-mel spectrogram.

    `log_mel` is (T=96, M=128). Convert back to power for energy weighting,
    then take the energy-weighted average mel-bin index, averaged over time.
    Range is [0, 127]; higher = energy concentrated in higher mel bins.
    """
    power = torch.exp(log_mel)  # (T, M)
    mel_bins = torch.arange(power.shape[1], dtype=torch.float32)
    total_energy = power.sum()
    centroid = (power.sum(dim=0) * mel_bins).sum() / (total_energy + 1e-8)
    return {"brightness": float(centroid.item())}


def _tertile_labels(values: List[float], labels=DENSITY_LABELS) -> List[str]:
    """Rank-based tertile bucketing: roughly equal-sized groups by rank,
    not by value range — robust to repeated values in small corpora.

    Returns a label per input value, in input order.
    """
    n = len(values)
    order = np.argsort(np.asarray(values), kind="stable")
    groups = np.array_split(order, len(labels))

    out = [""] * n
    for label, group in zip(labels, groups):
        for idx in group:
            out[idx] = label
    return out


def _build_matrix(row_labels: List[str], col_labels: List[str], rows, cols) -> dict:
    """Co-occurrence count matrix as {row_label: {col_label: count}}."""
    matrix = {r: {c: 0 for c in cols} for r in rows}
    for r, c in zip(row_labels, col_labels):
        matrix[r][c] += 1
    return matrix


def _format_matrix(matrix: dict, rows, cols, row_name: str, col_name: str) -> str:
    """Render a co-occurrence matrix as an ASCII table with a gap list."""
    col_width = max(len(c) for c in cols) + 2
    row_header_width = max(len(r) for r in rows) + 2

    lines = []
    lines.append(f"  {row_name} (rows) x {col_name} (cols)")
    header = " " * row_header_width + "".join(c.rjust(col_width) for c in cols)
    lines.append(header)
    for r in rows:
        line = r.ljust(row_header_width) + "".join(
            str(matrix[r][c]).rjust(col_width) for c in cols
        )
        lines.append(line)

    gaps = [(r, c) for r in rows for c in cols if matrix[r][c] == 0]
    if gaps:
        gap_str = ", ".join(f"({r}, {c})" for r, c in gaps)
        lines.append(f"  gaps (0 pairs): {gap_str}")
    else:
        lines.append("  gaps (0 pairs): none")

    return "\n".join(lines)


def _format_distribution(label: str, labels_in_order, counts: dict) -> str:
    parts = ", ".join(f"{lbl}={counts[lbl]}" for lbl in labels_in_order)
    return f"  {label}: {parts}"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Analyze rhythmic/timbral call-response relationships in a corpus."
    )
    parser.add_argument("pairs_root", help="Path to the data/pairs/ directory")
    parser.add_argument(
        "--tempo-bpm",
        type=float,
        default=120.0,
        help="Corpus tempo in bpm (default: 120.0; must match authored corpus)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional path to write a JSON dump of per-pair features + matrices",
    )
    args = parser.parse_args(argv)

    try:
        pairs = discover_pairs(args.pairs_root)
        if not pairs:
            print(f"No pairs found under {args.pairs_root}")
            return 0

        mel_extractor = MelExtractor()
        records = []
        for pair in pairs:
            call_notes = load_notes(
                str(pair.call_mid), str(pair.dir), tempo_bpm=args.tempo_bpm
            )
            resp_notes = load_notes(
                str(pair.response_mid), str(pair.dir), tempo_bpm=args.tempo_bpm
            )
            log_mel = mel_extractor(str(pair.call_wav), str(pair.dir))

            call_rhythm = _rhythmic_features(call_notes)
            resp_rhythm = _rhythmic_features(resp_notes)
            call_timbre = _timbral_features(log_mel)

            records.append(
                {
                    "nnn": pair.nnn,
                    "call": {**call_rhythm, **call_timbre},
                    "response": resp_rhythm,
                }
            )

        call_density = [r["call"]["density"] for r in records]
        resp_density = [r["response"]["density"] for r in records]
        call_articulation = [r["call"]["duration_ratio"] for r in records]
        resp_articulation = [r["response"]["duration_ratio"] for r in records]
        call_brightness = [r["call"]["brightness"] for r in records]
        resp_contour = [r["response"]["contour"] for r in records]

        call_density_labels = _tertile_labels(call_density, DENSITY_LABELS)
        resp_density_labels = _tertile_labels(resp_density, DENSITY_LABELS)
        call_articulation_labels = _tertile_labels(call_articulation, ARTICULATION_LABELS)
        resp_articulation_labels = _tertile_labels(resp_articulation, ARTICULATION_LABELS)
        call_brightness_labels = _tertile_labels(call_brightness, BRIGHTNESS_LABELS)

        density_matrix = _build_matrix(
            call_density_labels, resp_density_labels, DENSITY_LABELS, DENSITY_LABELS
        )
        articulation_matrix = _build_matrix(
            call_articulation_labels,
            resp_articulation_labels,
            ARTICULATION_LABELS,
            ARTICULATION_LABELS,
        )

        brightness_counts = {lbl: call_brightness_labels.count(lbl) for lbl in BRIGHTNESS_LABELS}
        contour_order = ("ascending", "descending", "static")
        contour_counts = {lbl: resp_contour.count(lbl) for lbl in contour_order}

        print(f"Corpus: {len(records)} pair(s) under {args.pairs_root}\n")
        print("Density complement (does response density echo or contrast the call?)")
        print(_format_matrix(density_matrix, DENSITY_LABELS, DENSITY_LABELS, "call density", "response density"))
        print()
        print("Articulation complement (staccato/legato relationship)")
        print(
            _format_matrix(
                articulation_matrix,
                ARTICULATION_LABELS,
                ARTICULATION_LABELS,
                "call articulation",
                "response articulation",
            )
        )
        print()
        print("Call brightness distribution (call-side only; response has no audio)")
        print(_format_distribution("brightness", BRIGHTNESS_LABELS, brightness_counts))
        print()
        print("Response contour distribution")
        print(_format_distribution("contour", contour_order, contour_counts))

        if args.output:
            for rec, cdl, rdl, cal, ral, cbl in zip(
                records,
                call_density_labels,
                resp_density_labels,
                call_articulation_labels,
                resp_articulation_labels,
                call_brightness_labels,
            ):
                rec["call"]["density_bucket"] = cdl
                rec["call"]["articulation_bucket"] = cal
                rec["call"]["brightness_bucket"] = cbl
                rec["response"]["density_bucket"] = rdl
                rec["response"]["articulation_bucket"] = ral

            dump = {
                "pairs": records,
                "density_matrix": density_matrix,
                "articulation_matrix": articulation_matrix,
                "call_brightness_distribution": brightness_counts,
                "response_contour_distribution": contour_counts,
            }
            with open(args.output, "w") as f:
                json.dump(dump, f, indent=2)
            print(f"\nWrote {args.output}")

        return 0

    except IngestError as e:
        print(f"INGEST FAILED: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"UNEXPECTED ERROR: {e!r}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
