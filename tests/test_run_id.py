"""Tests for compute_run_id determinism + sorted-input invariance (EVAL-03, D-09).

This file pins the exact byte stream that compute_run_id hashes. Any change
here invalidates every existing runs.jsonl entry — touch with deliberation.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from apollo.eval.run_id import compute_run_id


@pytest.fixture
def ckpt(tmp_path) -> Path:
    p = tmp_path / "fixture.pt"
    p.write_bytes(b"\x00\x01\x02\x03checkpoint-bytes\xff\xee")
    return p


def test_run_id_is_16_hex_chars(ckpt):
    rid = compute_run_id(str(ckpt), ["001", "002"])
    assert len(rid) == 16
    assert all(c in "0123456789abcdef" for c in rid)


def test_run_id_deterministic_across_calls(ckpt):
    rid = compute_run_id(str(ckpt), ["001", "002", "003"])
    for _ in range(10):
        assert compute_run_id(str(ckpt), ["001", "002", "003"]) == rid


def test_run_id_invariant_to_pair_id_order(ckpt):
    a = compute_run_id(str(ckpt), ["001", "002", "003"])
    b = compute_run_id(str(ckpt), ["003", "001", "002"])
    c = compute_run_id(str(ckpt), ["002", "003", "001"])
    assert a == b == c


def test_run_id_changes_with_different_pair_ids(ckpt):
    a = compute_run_id(str(ckpt), ["001", "002"])
    b = compute_run_id(str(ckpt), ["001", "003"])
    assert a != b


def test_run_id_changes_with_different_checkpoint_bytes(tmp_path):
    a_path = tmp_path / "a.pt"; a_path.write_bytes(b"AAAA")
    b_path = tmp_path / "b.pt"; b_path.write_bytes(b"BBBB")
    a = compute_run_id(str(a_path), ["001"])
    b = compute_run_id(str(b_path), ["001"])
    assert a != b


def test_run_id_matches_literal_formula(ckpt):
    """Pin the exact hash construction — any drift invalidates runs.jsonl."""
    h = hashlib.blake2b(digest_size=8)
    h.update(ckpt.read_bytes())
    h.update(b"\x00CORPUS\x00")
    for pid in sorted(["007", "003", "012"]):
        h.update(pid.encode("utf-8"))
        h.update(b"\x00")
    expected = h.hexdigest()
    assert compute_run_id(str(ckpt), ["007", "003", "012"]) == expected
