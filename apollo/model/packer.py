"""Boundary between Phase 1 artifact and Phase 2 training DataLoader.

Implements:
  - ApolloDataset: wraps an artifact["pairs"] list filtered by split
  - collate_fn:    packs [BOS, call, SEP, resp, EOS, PAD...] to MAX_SEQ_LEN

RESEARCH critical fixes baked in:
  - pad_mask is length-based, NEVER `token_ids == 0` (pitfall #1)
  - mel tensor channel dim added via .unsqueeze(1) (pitfall #6)
  - tokens cast to int64 (.long()) — nn.Embedding requires LongTensor
"""

from __future__ import annotations

import torch
from torch.utils.data import Dataset

from apollo.tokenizer import Vocab

_V = Vocab()
BOS = _V.BOS              # 109
EOS = _V.EOS              # 110
SEP = _V.SEP              # 111
PAD_ID = 0                # reuses TIME_OFFSET=0 (D-12); pad mask must be length-based
MAX_SEQ_LEN = 64          # D-08


class ApolloDataset(Dataset):
    """Wraps Phase 1 artifact pairs, filtered by split.

    Args:
        artifact: Pre-tokenized artifact dict from apollo.ingest.artifact.ingest().
        split:    One of "train" (non-heldout pairs), "held_out" (heldout pairs),
                  or "all" (every pair).
    """

    def __init__(self, artifact: dict, split: str = "train"):
        if split not in ("train", "all", "held_out"):
            raise ValueError(f"split must be one of train|all|held_out; got {split!r}")
        pairs = artifact["pairs"]
        if split == "all":
            self.entries = list(pairs)
        elif split == "train":
            self.entries = [e for e in pairs if not e["is_heldout"]]
        else:  # held_out
            self.entries = [e for e in pairs if e["is_heldout"]]

    def __len__(self) -> int:
        return len(self.entries)

    def __getitem__(self, idx: int) -> tuple:
        """Return (call_tokens, response_tokens, call_mel) for pair at idx.

        Tokens are returned as-is from the artifact (int32 tensors).
        collate_fn casts to int64. mel shape is (96, 128) float32.
        """
        e = self.entries[idx]
        return e["call_tokens"], e["response_tokens"], e["call_mel"]


def collate_fn(batch: list) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """Pack a batch of (call_tokens, response_tokens, mel) tuples.

    Sequence layout per TRAIN-01:
        [BOS, call_tokens..., SEP, response_tokens..., EOS, PAD..., PAD]
    padded to MAX_SEQ_LEN=64.

    Returns:
        token_ids: (B, MAX_SEQ_LEN) int64
        pad_mask:  (B, MAX_SEQ_LEN) bool, True at padding positions.
                   COMPUTED FROM SEQUENCE LENGTH — never from `token_ids == 0`
                   (RESEARCH pitfall #1: PAD_ID=0 collides with TIME bin 0).
        mel:       (B, 1, 96, 128) float32 (channel dim added here for Conv2d).
    """
    token_ids_list = []
    pad_mask_list = []
    mel_list = []

    for call_toks, resp_toks, mel in batch:
        seq = torch.cat([
            torch.tensor([BOS], dtype=torch.long),
            call_toks.long(),
            torch.tensor([SEP], dtype=torch.long),
            resp_toks.long(),
            torch.tensor([EOS], dtype=torch.long),
        ])
        L = int(seq.shape[0])
        assert L <= MAX_SEQ_LEN, (
            f"packed sequence length {L} exceeds MAX_SEQ_LEN={MAX_SEQ_LEN}"
        )

        padded = torch.full((MAX_SEQ_LEN,), PAD_ID, dtype=torch.long)
        padded[:L] = seq

        # Length-based pad mask — NOT value-based (RESEARCH pitfall #1)
        pad_mask = torch.zeros(MAX_SEQ_LEN, dtype=torch.bool)
        pad_mask[L:] = True

        token_ids_list.append(padded)
        pad_mask_list.append(pad_mask)
        mel_list.append(mel)

    token_ids = torch.stack(token_ids_list)                    # (B, 64)
    pad_mask = torch.stack(pad_mask_list)                      # (B, 64)
    mel_tensor = torch.stack(mel_list).unsqueeze(1).float()    # (B, 1, 96, 128)

    return token_ids, pad_mask, mel_tensor
