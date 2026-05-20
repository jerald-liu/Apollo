"""
MelEncoder — CNN mel spectrogram encoder for Apollo.

Compresses a (B, 1, 96, 128) mel tensor into a (B, d_model) conditioning vector.

Architecture (D-01 from Phase 2 CONTEXT.md):
    Conv2d(1→32, 3×3, pad=1) → ReLU → MaxPool2d(2)   # (B, 32, 48, 64)
    Conv2d(32→64, 3×3, pad=1) → ReLU → MaxPool2d(2)  # (B, 64, 24, 32)
    Conv2d(64→128, 3×3, pad=1) → ReLU                # (B, 128, 24, 32)
    AdaptiveAvgPool2d((1, 1))                         # (B, 128, 1, 1)
    Flatten → FC(128 → d_model)                       # (B, d_model)

Parameter count: 109,184 (verified in RESEARCH.md §4).

Joint training (D-02, COND-03):
    MelEncoder is jointly trained with the transformer. It MUST be passed to the
    same optimizer (or included as a submodule of the model passed to the optimizer).
    No frozen weights, no requires_grad=False.
"""

import torch
import torch.nn as nn


class MelEncoder(nn.Module):
    """CNN mel encoder. Input: (B, 1, 96, 128). Output: (B, d_model).

    Jointly trained with the transformer per D-02 — must be passed to the
    same optimizer (or be a submodule of the model passed to the optimizer).
    """

    def __init__(self, d_model: int = 128) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv2d(1,  32, kernel_size=3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
            nn.Conv2d(32, 64, kernel_size=3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
            nn.Conv2d(64, 128, kernel_size=3, padding=1), nn.ReLU(),
            nn.AdaptiveAvgPool2d((1, 1)),
        )
        self.fc = nn.Linear(128, d_model)

    def forward(self, mel: torch.Tensor) -> torch.Tensor:
        """
        Args:
            mel: (B, 1, 96, 128) float32 mel spectrogram tensor.
                 The channel dim (1) must be present — add it in the collate_fn
                 if the artifact stores mel as (96, 128).

        Returns:
            (B, d_model) float32 conditioning vector.
        """
        x = self.net(mel)   # (B, 128, 1, 1)
        x = x.flatten(1)    # (B, 128)
        return self.fc(x)   # (B, d_model)
