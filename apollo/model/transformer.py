"""Decoder-only transformer with MEL prefix injection (D-04 .. D-10).

Architecture (RESEARCH §1, §2):
  - nn.TransformerEncoderLayer with causal mask = decoder-only LM
  - MEL prefix injected at position 0 by torch.cat in forward
  - Positional embedding table size = max_seq_len + 1 (RESEARCH pitfall #4)
  - Float src_mask + bool src_key_padding_mask + is_causal=True together
    (RESEARCH pitfall #3; UserWarning suppressed)

Critical implementation notes:
  - pos_emb is nn.Embedding(max_seq_len + 1, d_model): positions 0..max_seq_len
    Position 0 = MEL prefix; positions 1..T = token positions.
  - TransformerEncoderLayer (NOT TransformerDecoderLayer) — see RESEARCH §1.
  - is_causal=True MUST accompany an explicit float src_mask (RESEARCH pitfall #3).
  - After transformer, drop out[:, 0] (MEL prefix position) before out_proj.
  - Do NOT call torch.compile (not supported on MPS in PyTorch 2.8).
"""

from __future__ import annotations

import warnings

import torch
import torch.nn as nn

from apollo.model.mel_encoder import MelEncoder


class ApolloModel(nn.Module):
    """Decoder-only transformer conditioned on a mel spectrogram prefix token.

    The mel tensor is passed through MelEncoder (a submodule) to produce a
    conditioning vector, which is injected as a prefix token at position 0
    before the BOS/call/SEP/response/EOS token sequence.

    Args:
        vocab_size:   Vocabulary size. Must match the tokenizer VOCAB_SIZE (256).
        d_model:      Model embedding dimension.
        n_layers:     Number of TransformerEncoderLayer stacks.
        n_heads:      Number of attention heads.
        d_ff:         Feed-forward dimension inside each encoder layer.
        max_seq_len:  Maximum token sequence length (not counting MEL prefix).
                      The positional embedding table has size max_seq_len+1
                      to accommodate MEL position 0 plus token positions 1..max_seq_len.
    """

    def __init__(
        self,
        vocab_size: int = 256,
        d_model: int = 128,
        n_layers: int = 4,
        n_heads: int = 4,
        d_ff: int = 512,
        max_seq_len: int = 64,
    ):
        super().__init__()
        self.vocab_size = vocab_size
        self.d_model = d_model
        self.max_seq_len = max_seq_len

        # MelEncoder is a submodule so model.parameters() covers it for the optimizer.
        self.mel_enc = MelEncoder(d_model=d_model)

        self.tok_emb = nn.Embedding(vocab_size, d_model)
        # +1 for the MEL prefix slot at position 0 (RESEARCH pitfall #4).
        # Allows positions 0..max_seq_len inclusive.
        self.pos_emb = nn.Embedding(max_seq_len + 1, d_model)

        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=n_heads,
            dim_feedforward=d_ff,
            batch_first=True,
            dropout=0.0,
            norm_first=False,   # Post-LN; avoids nested_tensor warning (RESEARCH §4)
        )
        # enable_nested_tensor=False: disables the MPS-incompatible nested tensor
        # fast path that raises NotImplementedError on MPS in eval mode when
        # src_key_padding_mask is provided (aten::_nested_tensor_from_mask_left_aligned).
        # Behavior is identical; only the internal dispatch path changes.
        self.transformer = nn.TransformerEncoder(
            encoder_layer, num_layers=n_layers, enable_nested_tensor=False
        )

        self.out_proj = nn.Linear(d_model, vocab_size)

    def forward(
        self,
        token_ids: torch.Tensor,                       # (B, T) int64
        mel_input: torch.Tensor,                       # (B, 1, 96, 128) float32
        key_padding_mask: torch.Tensor | None = None,  # (B, T) bool — True = padding
    ) -> torch.Tensor:                                 # (B, T, vocab_size)
        """
        Args:
            token_ids:         (B, T) int64 — packed token sequence
                               [BOS, call_tokens, SEP, resp_tokens, EOS, PAD...]
            mel_input:         (B, 1, 96, 128) float32 — mel spectrogram with channel dim
            key_padding_mask:  (B, T) bool — True marks padding positions in the TOKEN
                               sequence. Must be computed from sequence length, not from
                               token_ids == 0 (PAD_ID=0 is also a valid time_shift token).

        Returns:
            logits: (B, T, vocab_size) — next-token logits for every token position.
                    The MEL prefix output is dropped before projection; logit[:, j]
                    predicts token_ids[:, j+1].
        """
        B, T = token_ids.shape
        device = token_ids.device

        # Mel encoder: (B, 1, 96, 128) -> (B, d_model)
        mel_embed = self.mel_enc(mel_input)

        # Token embeddings at positions 1..T
        positions = torch.arange(1, T + 1, device=device).unsqueeze(0)  # (1, T)
        tok = self.tok_emb(token_ids) + self.pos_emb(positions)          # (B, T, d_model)

        # MEL prefix at position 0
        mel_pos = torch.zeros(B, 1, dtype=torch.long, device=device)
        mel_prefix = mel_embed.unsqueeze(1) + self.pos_emb(mel_pos)      # (B, 1, d_model)

        # Concatenate: [mel_prefix, token_embeddings] -> (B, 1+T, d_model)
        x = torch.cat([mel_prefix, tok], dim=1)
        total_len = 1 + T

        # Float causal mask covering the full concatenated length (1+T).
        # Upper triangle = -inf; diagonal/lower triangle = 0 (can attend).
        causal = torch.full(
            (total_len, total_len), float("-inf"), device=device
        ).triu(1)

        # Prepend False for the MEL prefix position (it is never padding)
        # before passing to the transformer (which sees 1+T positions).
        if key_padding_mask is not None:
            mel_not_pad = torch.zeros(B, 1, dtype=torch.bool, device=device)
            full_pad = torch.cat([mel_not_pad, key_padding_mask], dim=1)  # (B, 1+T)
        else:
            full_pad = None

        with warnings.catch_warnings():
            # Suppress: "Support for mismatched src_key_padding_mask and src_mask is
            # deprecated" — triggered by float mask + bool padding mask combination.
            # This is a deprecation warning, not an error; both masks are applied
            # correctly. See RESEARCH §3.
            warnings.simplefilter("ignore", UserWarning)
            out = self.transformer(
                x,
                mask=causal,
                src_key_padding_mask=full_pad,
                is_causal=True,
            )

        # Drop the MEL prefix output (position 0), project token positions to vocab.
        return self.out_proj(out[:, 1:])  # (B, T, vocab_size)
