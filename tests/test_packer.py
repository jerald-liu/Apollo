"""Contract tests for ApolloDataset + collate_fn (Plan 02-03).

Tests pin down:
  - Dataset split filtering (train / held_out / all)
  - __getitem__ return shapes and dtypes
  - collate_fn output shapes and dtypes
  - Exact [BOS, call, SEP, resp, EOS, PAD...] sequence layout
  - Length-based pad mask (RESEARCH pitfall #1: PAD_ID=0 collides with TIME bin 0)
  - Over-long sequence raises AssertionError
  - Vocab constant contract (BOS=109, EOS=110, SEP=111, PAD_ID=0, MAX_SEQ_LEN=64)
  - Standard DataLoader integration
"""

from __future__ import annotations

import pytest
import torch
from torch.utils.data import DataLoader

from apollo.model import ApolloDataset, collate_fn
from apollo.tokenizer import Vocab


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def artifact(tmp_path_factory):
    """Build a real 6-pair artifact with a mix of heldout / non-heldout pairs.

    NNNs 000–004 are non-heldout; NNN 006 is heldout (verified by is_heldout()).
    This gives 5 train + 1 held_out = 6 total.
    """
    from apollo.ingest.mock import synthesize_pair
    from apollo.ingest.artifact import ingest

    root = tmp_path_factory.mktemp("pairs")
    # 5 non-heldout pairs
    for i in range(5):
        synthesize_pair(root, nnn=f"{i:03d}")
    # 1 heldout pair (006 is_heldout=True)
    synthesize_pair(root, nnn="006")

    return ingest(str(root))


# ---------------------------------------------------------------------------
# Dataset length tests
# ---------------------------------------------------------------------------

def test_dataset_len_train(artifact):
    """split='train' length equals the count of non-heldout entries."""
    expected = sum(1 for e in artifact["pairs"] if not e["is_heldout"])
    ds = ApolloDataset(artifact, split="train")
    assert len(ds) == expected


def test_dataset_len_held_out(artifact):
    """split='held_out' length equals the count of heldout entries."""
    expected = sum(1 for e in artifact["pairs"] if e["is_heldout"])
    ds = ApolloDataset(artifact, split="held_out")
    assert len(ds) == expected


def test_dataset_len_all(artifact):
    """split='all' length equals the total pair count (6)."""
    ds = ApolloDataset(artifact, split="all")
    assert len(ds) == len(artifact["pairs"])


# ---------------------------------------------------------------------------
# __getitem__ shape / dtype tests
# ---------------------------------------------------------------------------

def test_dataset_getitem_shapes(artifact):
    """__getitem__ returns a 3-tuple (call_tokens, response_tokens, mel).

    mel must have shape (96, 128) and dtype float32.
    Tokens are 1-D tensors (LongTensor or IntTensor).
    """
    ds = ApolloDataset(artifact, split="all")
    call_toks, resp_toks, mel = ds[0]

    assert isinstance(call_toks, torch.Tensor), "call_tokens must be a tensor"
    assert isinstance(resp_toks, torch.Tensor), "response_tokens must be a tensor"
    assert isinstance(mel, torch.Tensor), "mel must be a tensor"

    assert call_toks.ndim == 1, f"call_tokens must be 1-D, got {call_toks.ndim}-D"
    assert resp_toks.ndim == 1, f"response_tokens must be 1-D, got {resp_toks.ndim}-D"
    assert mel.shape == (96, 128), f"mel shape must be (96, 128), got {mel.shape}"
    assert mel.dtype == torch.float32, f"mel dtype must be float32, got {mel.dtype}"


# ---------------------------------------------------------------------------
# collate_fn output shape / dtype tests
# ---------------------------------------------------------------------------

def test_collate_fn_output_shapes(artifact):
    """collate_fn over 4 items returns correctly-shaped and -typed tensors."""
    ds = ApolloDataset(artifact, split="all")
    batch = [ds[i] for i in range(4)]
    token_ids, pad_mask, mel = collate_fn(batch)

    assert token_ids.shape == (4, 64), f"token_ids shape mismatch: {token_ids.shape}"
    assert token_ids.dtype == torch.int64, f"token_ids dtype must be int64: {token_ids.dtype}"
    assert pad_mask.shape == (4, 64), f"pad_mask shape mismatch: {pad_mask.shape}"
    assert pad_mask.dtype == torch.bool, f"pad_mask dtype must be bool: {pad_mask.dtype}"
    assert mel.shape == (4, 1, 96, 128), f"mel shape mismatch: {mel.shape}"
    assert mel.dtype == torch.float32, f"mel dtype must be float32: {mel.dtype}"


# ---------------------------------------------------------------------------
# Sequence layout test
# ---------------------------------------------------------------------------

def test_collate_fn_sequence_layout(artifact):
    """Packed token IDs follow exact [BOS, call, SEP, resp, EOS, PAD...] layout."""
    _V = Vocab()
    BOS = _V.BOS    # 109
    EOS = _V.EOS    # 110
    SEP = _V.SEP    # 111
    PAD_ID = 0

    ds = ApolloDataset(artifact, split="all")
    call_toks, resp_toks, mel = ds[0]

    token_ids, _pad_mask, _mel = collate_fn([(call_toks, resp_toks, mel)])

    ids = token_ids[0]
    C = int(call_toks.shape[0])
    R = int(resp_toks.shape[0])

    # BOS at position 0
    assert int(ids[0]) == BOS, f"ids[0] must be BOS={BOS}, got {ids[0]}"
    # call_tokens at positions 1..C
    for i in range(C):
        assert int(ids[1 + i]) == int(call_toks[i].long()), (
            f"call token mismatch at offset {i}: expected {call_toks[i]}, got {ids[1+i]}"
        )
    # SEP
    assert int(ids[1 + C]) == SEP, f"ids[{1+C}] must be SEP={SEP}, got {ids[1+C]}"
    # response tokens
    for i in range(R):
        assert int(ids[1 + C + 1 + i]) == int(resp_toks[i].long()), (
            f"response token mismatch at offset {i}"
        )
    # EOS
    assert int(ids[1 + C + 1 + R]) == EOS, (
        f"ids[{1+C+1+R}] must be EOS={EOS}, got {ids[1+C+1+R]}"
    )
    # PAD from EOS+1 to end
    seq_len = 1 + C + 1 + R + 1  # BOS + call + SEP + resp + EOS
    assert (ids[seq_len:] == PAD_ID).all(), "all positions after EOS must be PAD_ID=0"


# ---------------------------------------------------------------------------
# Pad mask is length-based (RESEARCH pitfall #1)
# ---------------------------------------------------------------------------

def test_pad_mask_is_length_based_not_value_based(artifact):
    """Pad mask must be derived from sequence length, NOT from token_ids == 0.

    We build a synthetic batch entry where call_tokens[0] = 0 (TIME bin 0, a
    valid token). If pad_mask is computed as `token_ids == 0`, position 1 would
    be falsely marked as padding. The correct implementation marks it as NOT
    padding because it is inside the real sequence.
    """
    # Build a synthetic entry: call_tokens starts with TIME bin 0
    call_toks = torch.tensor([0, 5, 10], dtype=torch.int32)   # 0 is TIME_OFFSET=0 (valid!)
    resp_toks  = torch.tensor([32, 69, 85, 110], dtype=torch.int32)  # pitch, vel, dur, EOS-ish value
    mel        = torch.zeros(96, 128, dtype=torch.float32)

    token_ids, pad_mask, _mel = collate_fn([(call_toks, resp_toks, mel)])

    # Sequence: [BOS, 0, 5, 10, SEP, 32, 69, 85, 110, EOS, PAD, ...]
    # Position 1 holds value 0 (call_toks[0] = TIME bin 0) — it is REAL, not padding
    assert pad_mask[0, 1] == False, (
        "position 1 has value 0 but is inside the real sequence; pad_mask must be False there"
    )

    # Compute actual sequence length
    C = call_toks.shape[0]
    R = resp_toks.shape[0]
    actual_len = 1 + C + 1 + R + 1  # BOS + call + SEP + resp + EOS

    # All positions past the real sequence must be True (padding)
    assert pad_mask[0, actual_len:].all(), (
        "positions past the real sequence must all be True (padding)"
    )
    # All positions inside the real sequence must be False (not padding)
    assert pad_mask[0, :actual_len].sum() == 0, (
        "all positions inside the real sequence must be False (not padding)"
    )


# ---------------------------------------------------------------------------
# Over-long sequence raises
# ---------------------------------------------------------------------------

def test_collate_fn_raises_when_too_long():
    """collate_fn raises AssertionError when packed sequence would exceed MAX_SEQ_LEN=64."""
    # call_tokens of length 60 → packed = 1 (BOS) + 60 + 1 (SEP) + 1 (resp) + 1 (EOS) = 64
    # Add one more response token to go over: 65 > 64
    call_toks = torch.zeros(60, dtype=torch.int32)
    resp_toks = torch.zeros(3, dtype=torch.int32)   # 1+60+1+3+1 = 66 > 64
    mel       = torch.zeros(96, 128, dtype=torch.float32)

    with pytest.raises((AssertionError, ValueError)):
        collate_fn([(call_toks, resp_toks, mel)])


# ---------------------------------------------------------------------------
# Vocab constant contract
# ---------------------------------------------------------------------------

def test_constants_match_vocab():
    """Packer constants must match Vocab — BOS=109, EOS=110, SEP=111, PAD_ID=0, MAX_SEQ_LEN=64."""
    from apollo.model.packer import BOS, EOS, SEP, PAD_ID, MAX_SEQ_LEN

    _V = Vocab()
    assert BOS == _V.BOS == 109,      f"BOS mismatch: packer={BOS}, Vocab={_V.BOS}"
    assert EOS == _V.EOS == 110,      f"EOS mismatch: packer={EOS}, Vocab={_V.EOS}"
    assert SEP == _V.SEP == 111,      f"SEP mismatch: packer={SEP}, Vocab={_V.SEP}"
    assert PAD_ID == 0,               f"PAD_ID mismatch: packer={PAD_ID}"
    assert MAX_SEQ_LEN == 64,         f"MAX_SEQ_LEN mismatch: packer={MAX_SEQ_LEN}"


# ---------------------------------------------------------------------------
# DataLoader integration
# ---------------------------------------------------------------------------

def test_dataloader_integration(artifact):
    """Standard torch DataLoader with collate_fn works end-to-end."""
    ds = ApolloDataset(artifact, split="all")
    loader = DataLoader(ds, batch_size=2, collate_fn=collate_fn, shuffle=False)

    batch = next(iter(loader))
    token_ids, pad_mask, mel = batch

    assert token_ids.shape == (2, 64), f"token_ids shape: {token_ids.shape}"
    assert token_ids.dtype == torch.int64
    assert pad_mask.shape == (2, 64), f"pad_mask shape: {pad_mask.shape}"
    assert pad_mask.dtype == torch.bool
    assert mel.shape == (2, 1, 96, 128), f"mel shape: {mel.shape}"
    assert mel.dtype == torch.float32
