"""Tests for deterministic hash-based held-out split (DATA-04).

Covers `apollo.ingest.split.is_heldout` and `normalize_nnn`.

The split is computed as `int(sha1(nnn).hexdigest(), 16) % 5 == 0` per
CONTEXT.md D-20 and RESEARCH.md §"Deterministic Split". This test file is
the contract that pins that exact formula — any change here means
existing held-out assignments shift, which would corrupt training/eval.
"""

from __future__ import annotations

import hashlib

import pytest

from apollo.ingest.split import is_heldout, normalize_nnn


def test_is_heldout_deterministic_across_calls():
    """Calling is_heldout('001') ten times in a row must return the same bool."""
    value = is_heldout("001")
    for _ in range(10):
        assert is_heldout("001") == value


def test_split_is_deterministic_across_runs():
    """is_heldout must match the literal sha1 mod 5 formula for all NNNs in 000..049."""
    nnns = [f"{i:03d}" for i in range(50)]
    expected_heldout = {
        nnn
        for nnn in nnns
        if int(hashlib.sha1(nnn.encode("utf-8")).hexdigest(), 16) % 5 == 0
    }
    for nnn in nnns:
        assert is_heldout(nnn) == (nnn in expected_heldout), (
            f"is_heldout({nnn!r}) disagrees with sha1 mod 5 formula"
        )


def test_split_ratio_approximately_20_percent():
    """For N=200 synthetic NNNs, count of heldout must be in [30, 50] (binomial slack)."""
    nnns = [f"{i:03d}" for i in range(200)]
    count = sum(1 for nnn in nnns if is_heldout(nnn))
    assert 30 <= count <= 50, (
        f"expected ~40 heldout (20% of 200) ± slack; got {count}"
    )


def test_normalize_nnn_strips_whitespace():
    assert normalize_nnn("  001\n") == "001"


def test_normalize_nnn_empty_raises():
    with pytest.raises(ValueError):
        normalize_nnn("   ")


def test_renaming_changes_split():
    """Renaming a folder is a new identity — is_heldout('001') and ('031') are independent."""
    # The two NNNs are different strings, so their hash splits are independent.
    # We don't assert they differ (they might happen to agree), only that the
    # function treats them as independent keys (i.e. doesn't normalize them to
    # the same thing). normalize_nnn preserves the string as-is modulo strip.
    assert normalize_nnn("001") != normalize_nnn("031")
    # And both are deterministic individually (re-checked here for clarity).
    assert is_heldout("001") == is_heldout("001")
    assert is_heldout("031") == is_heldout("031")
