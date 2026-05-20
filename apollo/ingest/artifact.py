"""Pre-tokenized artifact: a single `.pt` dict bundling tokens + mel + metadata.

This module is the API contract with Phase 2 — see RESEARCH.md §"Pre-tokenized
Artifact Schema" for the full schema dict and field-by-field rationale.

Format: a single `torch.save`-able dict-of-tensors with explicit schema
versioning. `load_artifact` uses `torch.load(..., weights_only=False)` because
the file is OUR file in OUR repo (T-01-14 disposition: accept). Third-party
artifacts MUST NOT be loaded with `weights_only=False` — add a hash check or
use `weights_only=True` at that point.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import torch

import apollo
from apollo.ingest.audio import MelExtractor
from apollo.ingest.errors import IngestError  # re-export not needed; used by callers
from apollo.ingest.midi import load_notes
from apollo.ingest.pairs import discover_pairs
from apollo.ingest.split import is_heldout
from apollo.tokenizer import Tokenizer, Vocab
from apollo.tokenizer.bins import DURATION_EDGES


SCHEMA_VERSION = 1


def _vocab_dict(vocab: Vocab, tempo_bpm: float) -> dict:
    """Mirror the Vocab dataclass into a plain dict, plus tempo + duration edges.

    The artifact freezes the vocab table at ingest time so a future Vocab
    refactor cannot silently break older checkpoints.
    """
    return {
        "PITCH_MIN":       vocab.PITCH_MIN,
        "PITCH_MAX":       vocab.PITCH_MAX,
        "N_PITCH":         vocab.N_PITCH,
        "N_TIME":          vocab.N_TIME,
        "N_VELOCITY":      vocab.N_VELOCITY,
        "N_DURATION":      vocab.N_DURATION,
        "TIME_OFFSET":     vocab.TIME_OFFSET,
        "PITCH_OFFSET":    vocab.PITCH_OFFSET,
        "VELOCITY_OFFSET": vocab.VELOCITY_OFFSET,
        "DURATION_OFFSET": vocab.DURATION_OFFSET,
        "BOS":             vocab.BOS,
        "EOS":             vocab.EOS,
        "SEP":             vocab.SEP,
        "VOCAB_SIZE":      vocab.VOCAB_SIZE,
        "ACTIVE_VOCAB":    vocab.ACTIVE_VOCAB,
        "tempo_bpm":       float(tempo_bpm),
        "duration_edges":  [float(x) for x in DURATION_EDGES],
    }


def _mel_config_dict() -> dict:
    """Mirror MelExtractor's class-level config into the artifact."""
    return {
        "sample_rate":   MelExtractor.TARGET_SR,
        "n_fft":         MelExtractor.N_FFT,
        "hop_length":    MelExtractor.HOP_LENGTH,
        "n_mels":        MelExtractor.N_MELS,
        "target_frames": MelExtractor.TARGET_FRAMES,
        "log_floor":     MelExtractor.LOG_FLOOR,
    }


def ingest(root: str, tempo_bpm: float = 120.0) -> dict:
    """Run the full pipeline: discover pairs, tokenize, mel-extract, assign splits.

    Returns the schema-versioned artifact dict (NOT saved here — call
    `save_artifact` to write it to disk). Pairs in the output are in
    deterministic (sorted-by-nnn) order because `discover_pairs` sorts.
    Per-pair `IngestError`s propagate up to the caller (the CLI maps them
    to exit code 1).
    """
    vocab = Vocab()
    mel_extractor = MelExtractor()
    pairs_paths = discover_pairs(root)

    entries = []
    n_heldout = 0
    for pp in pairs_paths:
        tokenizer = Tokenizer(
            vocab=vocab, tempo_bpm=tempo_bpm, pair_path=str(pp.dir)
        )
        call_notes = load_notes(
            str(pp.call_mid), str(pp.dir), tempo_bpm=tempo_bpm
        )
        response_notes = load_notes(
            str(pp.response_mid), str(pp.dir), tempo_bpm=tempo_bpm
        )
        call_tokens = torch.tensor(
            tokenizer.encode(call_notes), dtype=torch.int32
        )
        response_tokens = torch.tensor(
            tokenizer.encode(response_notes), dtype=torch.int32
        )
        call_mel = mel_extractor(str(pp.call_wav), str(pp.dir))  # (96, 128) f32
        heldout = is_heldout(pp.nnn)
        if heldout:
            n_heldout += 1
        entries.append(
            {
                "nnn":             pp.nnn,
                "is_heldout":      heldout,
                "call_tokens":     call_tokens,
                "response_tokens": response_tokens,
                "call_mel":        call_mel,
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "vocab":          _vocab_dict(vocab, tempo_bpm),
        "mel_config":     _mel_config_dict(),
        "pairs":          entries,
        "metadata": {
            "ingest_timestamp": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            "source_root":    str(Path(root).resolve()),
            "n_pairs":        len(entries),
            "n_heldout":      n_heldout,
            "apollo_version": apollo.__version__,
        },
    }


def save_artifact(artifact: dict, out_path: str) -> None:
    """Write the artifact dict to `out_path` via `torch.save`.

    Creates the parent directory if it doesn't exist (so `artifacts/...`
    works on a fresh clone without manual mkdir).
    """
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    torch.save(artifact, str(out))


def load_artifact(in_path: str) -> dict:
    """Load and validate the artifact at `in_path`.

    Uses `weights_only=False` because the file is OUR file. Do NOT use this
    loader on third-party artifacts (see T-01-14 in PLAN.md threat model).
    """
    data = torch.load(in_path, map_location="cpu", weights_only=False)
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"unsupported schema_version: {data.get('schema_version')}, "
            f"expected {SCHEMA_VERSION}"
        )
    return data
