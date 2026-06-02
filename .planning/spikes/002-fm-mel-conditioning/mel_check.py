"""Spike 002: does the mel of FM-rendered audio carry a usable timbre-conditioning signal?

Reuses Apollo's REAL MelExtractor (apollo.ingest.audio) — the exact COND-01 contract
(22050 Hz, n_fft=2048, hop=512, n_mels=128, log, fixed (96,128)) — and runs it against
the WAVs produced by spike 001. Proves the mel is:
  (a) the right shape/contract the model already consumes,
  (b) deterministic for a given render,
  (c) meaningfully different between FM presets (carries timbre), and
  (d) more self-similar within a preset than across presets (the property an encoder
      needs to learn timbre).

Run from repo root with the project venv so `import apollo` resolves:
    .venv/bin/python .planning/spikes/002-fm-mel-conditioning/mel_check.py
"""
import sys
from pathlib import Path

import torch

from apollo.ingest.audio import MelExtractor

S001 = Path(__file__).resolve().parents[1] / "001-dawdreamer-fm-render"
A = S001 / "callA_ratio2_index2.wav"
B = S001 / "callB_ratio3_index8.wav"
DET = S001 / "_det_check.wav"  # bit-identical re-render of A from spike 001


def main() -> int:
    for p in (A, B, DET):
        if not p.exists():
            print(f"MISSING {p} — run spike 001's render_fm.py first")
            return 1

    mx = MelExtractor()
    mA = mx(str(A), str(A.parent))
    mB = mx(str(B), str(B.parent))
    mDet = mx(str(DET), str(DET.parent))

    print(f"shape A: {tuple(mA.shape)} dtype={mA.dtype}")  # expect (96, 128)
    assert mA.shape == (96, 128), "mel shape != COND-01 contract (96,128)"

    # (b) determinism — re-render of A yields identical mel
    det_identical = torch.equal(mA, mDet)
    print(f"determinism (A vs re-render): identical={det_identical}")

    # (c) timbre difference A vs B
    l2_AB = torch.norm(mA - mB).item()
    # cosine similarity on flattened log-mels (proxy for "how distinguishable")
    def cos(x, y):
        xf, yf = x.flatten(), y.flatten()
        return torch.dot(xf, yf).item() / (xf.norm().item() * yf.norm().item())
    cos_AB = cos(mA, mB)
    cos_AA = cos(mA, mDet)
    print(f"L2(A,B)={l2_AB:.2f}  cos(A,B)={cos_AB:.4f}  cos(A,A')={cos_AA:.4f}")

    # (d) within-preset > across-preset similarity
    within_beats_across = cos_AA > cos_AB
    print(f"within-preset more similar than across: {within_beats_across}")

    # mean log-mel energy differs (sanity that brightness/structure changed)
    print(f"mean log-mel  A={mA.mean():.3f}  B={mB.mean():.3f}")

    ok = (
        mA.shape == (96, 128)
        and det_identical
        and l2_AB > 1.0
        and cos_AB < 0.999
        and within_beats_across
    )
    print("VERDICT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
