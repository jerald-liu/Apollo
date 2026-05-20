"""End-to-end ingest smoke test on synthetic mock pairs.

Exercises the full pipeline (discover → load_notes → tokenize → mel-extract
→ artifact dict → torch.save → torch.load) on pairs synthesized in tmp_path.
This is the only test module that runs ingest() against real files on disk.

Phase 01 Plan 05 — final integration test for the ingest stack.
"""

from __future__ import annotations

import time

import pytest
import torch

from apollo.ingest import (
    ingest,
    save_artifact,
    load_artifact,
    synthesize_pair,
    is_heldout,
)


def test_synthesize_pair_creates_three_files(tmp_path):
    pair_dir = synthesize_pair(tmp_path, nnn="000")
    assert (pair_dir / "call.mid").is_file()
    assert (pair_dir / "call.wav").is_file()
    assert (pair_dir / "response.mid").is_file()


def test_ingest_ten_pairs_end_to_end(tmp_path):
    for i in range(10):
        synthesize_pair(tmp_path, nnn=f"{i:03d}")

    artifact = ingest(str(tmp_path))

    assert artifact["schema_version"] == 1
    assert len(artifact["pairs"]) == 10

    # Sort order: pairs come out in nnn-ascending order
    assert [p["nnn"] for p in artifact["pairs"]] == [f"{i:03d}" for i in range(10)]

    # Each pair entry has the 5 required keys
    required_keys = {"nnn", "is_heldout", "call_tokens", "response_tokens", "call_mel"}
    for p in artifact["pairs"]:
        assert required_keys.issubset(set(p.keys()))

    p0 = artifact["pairs"][0]
    assert p0["call_tokens"].dtype == torch.int32
    assert p0["response_tokens"].dtype == torch.int32
    assert p0["call_tokens"].ndim == 1
    assert p0["call_tokens"].shape[0] % 4 == 0
    assert p0["response_tokens"].shape[0] % 4 == 0
    assert p0["call_mel"].shape == (96, 128)
    assert p0["call_mel"].dtype == torch.float32

    assert artifact["metadata"]["n_pairs"] == 10
    expected_heldout = sum(is_heldout(f"{i:03d}") for i in range(10))
    assert artifact["metadata"]["n_heldout"] == expected_heldout


def test_artifact_round_trip(tmp_path):
    for i in range(5):
        synthesize_pair(tmp_path, nnn=f"{i:03d}")

    original = ingest(str(tmp_path))
    out_path = tmp_path / "out.pt"
    save_artifact(original, str(out_path))
    loaded = load_artifact(str(out_path))

    assert loaded["schema_version"] == 1
    assert loaded["metadata"]["n_pairs"] == 5
    assert len(loaded["pairs"]) == len(original["pairs"]) == 5

    for i in range(5):
        lp = loaded["pairs"][i]
        op = original["pairs"][i]
        assert lp["nnn"] == op["nnn"]
        assert torch.equal(lp["call_tokens"], op["call_tokens"])
        assert torch.equal(lp["response_tokens"], op["response_tokens"])
        assert torch.equal(lp["call_mel"], op["call_mel"])


def test_nnn_gaps_allowed(tmp_path):
    # Skip "002" — NNN gaps are explicitly supported (D-17)
    for nnn in ("000", "001", "003", "004"):
        synthesize_pair(tmp_path, nnn=nnn)

    artifact = ingest(str(tmp_path))
    assert len(artifact["pairs"]) == 4
    assert [p["nnn"] for p in artifact["pairs"]] == ["000", "001", "003", "004"]


def test_end_to_end_under_ten_seconds(tmp_path):
    for i in range(10):
        synthesize_pair(tmp_path, nnn=f"{i:03d}")

    t0 = time.perf_counter()
    artifact = ingest(str(tmp_path))
    elapsed = time.perf_counter() - t0
    assert elapsed < 10.0, f"ingest took {elapsed:.2f}s (limit 10.0s)"
    assert len(artifact["pairs"]) == 10
