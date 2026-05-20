"""Tests for train.py loss mask, metrics, and training loop.

TDD RED phase — all tests must fail with ImportError until implementation is added.

Loss mask contract (TRAIN-02):
  - `j >= sep_pos` boundary — includes first response token, excludes SEP
  - Call/BOS/SEP positions excluded from gradient

Metrics contract (TRAIN-04 prep):
  - token_category: correct category boundaries
  - compute_type_accuracy: response-only, same j >= sep_pos mask

Train step contract (TRAIN-03, TRAIN-05):
  - MPS step executes without error
  - Random init confirmed (no load_state_dict)
  - mel_enc params update (jointly trained)
  - 30-epoch mask-direction verification (response CE < call CE)
"""

from __future__ import annotations

import subprocess
import sys
import tempfile

import pytest
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader

from apollo.model import ApolloModel, ApolloDataset, collate_fn, BOS, EOS, SEP
from apollo.model.train import compute_masked_loss, train_epoch, get_device
from apollo.model.metrics import token_category, compute_type_accuracy

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def mock_artifact(tmp_path_factory):
    """Build a 7-pair mock artifact using synthesize_pair + ingest.

    synthesize_pair(root, nnn=...) creates <root>/<nnn>/{call.mid,call.wav,response.mid}.
    NNNs 000-005 are non-heldout; 006 is heldout (deterministic from is_heldout logic).
    """
    from apollo.ingest.mock import synthesize_pair
    from apollo.ingest.artifact import ingest

    root = tmp_path_factory.mktemp("pairs")
    for i in range(6):
        synthesize_pair(root, nnn=f"{i:03d}")
    synthesize_pair(root, nnn="006")  # heldout pair for coverage

    artifact = ingest(root)
    return artifact


@pytest.fixture(scope="module")
def train_dataloader(mock_artifact):
    """DataLoader over the train split of the mock artifact."""
    dataset = ApolloDataset(mock_artifact, split="train")
    return DataLoader(dataset, batch_size=2, collate_fn=collate_fn, shuffle=False)


# ---------------------------------------------------------------------------
# LOSS MASK CONTRACT TESTS (TRAIN-02)
# ---------------------------------------------------------------------------


class TestLossMaskBoundary:
    """Pin the j >= sep_pos boundary."""

    def _make_batch(self, sep_idx: int = 5, T: int = 16, V: int = 256):
        """Build a (1, T) token_ids and (1, T, V) logits with SEP at sep_idx."""
        token_ids = torch.zeros(1, T, dtype=torch.long)
        token_ids[0, sep_idx] = SEP  # place SEP at sep_idx

        # Fill in some plausible-ish token IDs around the SEP
        for j in range(1, sep_idx):
            token_ids[0, j] = j % 32  # call tokens: time bins
        for j in range(sep_idx + 1, T - 1):
            token_ids[0, j] = 32 + (j % 37)  # response tokens: pitch range
        token_ids[0, T - 1] = EOS

        # Logits: uniform (predicts nothing in particular)
        logits = torch.ones(1, T, V)
        return logits, token_ids

    def test_loss_mask_uses_geq_sep_pos(self):
        """Direct boundary pin: position j=sep_pos is INCLUDED (j >= sep_pos).

        Strategy: build logits that are perfect on positions j < sep_pos
        and imperfect at j = sep_pos. Loss on the call-region-only batch
        should be ~0; loss with j=sep_pos included should be > 0.
        """
        T, V = 16, 256
        sep_idx = 5

        logits, token_ids = self._make_batch(sep_idx=sep_idx, T=T, V=V)

        # Make logits predict the correct token everywhere (uniform → argmax arbitrary)
        # We'll be precise: make logits score target perfectly at every position.
        logits_perfect = torch.full((1, T, V), -10.0)
        for j in range(T - 1):
            target = token_ids[0, j + 1].item()
            logits_perfect[0, j, target] = 10.0

        # Perturb only at position j < sep_pos (j=3 → predicts token_ids[4])
        # Response loss should remain ~0 (call excluded from mask)
        logits_perturb_call = logits_perfect.clone()
        wrong_token = (token_ids[0, 4].item() + 1) % V
        logits_perturb_call[0, 3, token_ids[0, 4].item()] = -10.0
        logits_perturb_call[0, 3, wrong_token] = 10.0

        loss_call_perturbed = compute_masked_loss(logits_perturb_call, token_ids)
        assert loss_call_perturbed.item() < 1e-3, (
            f"Perturbation at j < sep_pos should not change response loss, got {loss_call_perturbed.item()}"
        )

        # Perturb at j = sep_pos (predicts token_ids[sep_pos+1], the FIRST response token)
        # Response loss should be > 0 (this position IS included)
        logits_perturb_resp0 = logits_perfect.clone()
        wrong_token2 = (token_ids[0, sep_idx + 1].item() + 1) % V
        logits_perturb_resp0[0, sep_idx, token_ids[0, sep_idx + 1].item()] = -10.0
        logits_perturb_resp0[0, sep_idx, wrong_token2] = 10.0

        loss_resp0_perturbed = compute_masked_loss(logits_perturb_resp0, token_ids)
        assert loss_resp0_perturbed.item() > 1e-3, (
            f"Perturbation at j=sep_pos should increase response loss (first response token included), "
            f"got {loss_resp0_perturbed.item()}"
        )

    def test_loss_mask_excludes_bos_call_sep(self):
        """Perturbing logits at BOS, call, and SEP positions leaves response loss unchanged."""
        T, V = 16, 256
        sep_idx = 5
        logits, token_ids = self._make_batch(sep_idx=sep_idx, T=T, V=V)

        base_loss = compute_masked_loss(logits, token_ids)

        # Perturb at positions j = 0 (BOS predicted), 1, 2 (call tokens), sep_idx-1 (SEP predicted)
        logits_perturbed = logits.clone()
        for perturb_j in [0, 1, 2, sep_idx - 1]:
            logits_perturbed[0, perturb_j, :] = 0.0
            logits_perturbed[0, perturb_j, 0] = 100.0

        perturbed_loss = compute_masked_loss(logits_perturbed, token_ids)

        assert abs(base_loss.item() - perturbed_loss.item()) < 1e-5, (
            f"Perturbing BOS/call/SEP logits should not change response loss. "
            f"Base={base_loss.item():.6f}, Perturbed={perturbed_loss.item():.6f}"
        )

    def test_loss_mask_includes_first_response_token(self):
        """Changing target of first response position changes loss (> 1e-6 difference).

        Uses non-uniform logits at j=sep_pos so the specific target token matters.
        With uniform logits CE is identical for any target — that would be a tautology,
        not a mask test.
        """
        T, V = 16, 256
        sep_idx = 5

        # Build token_ids with SEP at sep_idx
        token_ids = torch.zeros(1, T, dtype=torch.long)
        token_ids[0, sep_idx] = SEP
        first_resp_token = 50  # arbitrary pitch token
        token_ids[0, sep_idx + 1] = first_resp_token
        for j in range(sep_idx + 2, T - 1):
            token_ids[0, j] = 32 + (j % 37)
        token_ids[0, T - 1] = EOS

        # Non-uniform logits: at j=sep_pos, strongly score token 0 (NOT the correct target)
        logits = torch.zeros(1, T, V)
        logits[0, sep_idx, 0] = 10.0  # argmax=0, target=first_resp_token=50 → high loss

        # Loss with original first response target (50) — high because logits point away
        loss_original = compute_masked_loss(logits, token_ids)

        # Swap first response target to token 0 — logits now point AT target → low loss
        token_ids_alt = token_ids.clone()
        token_ids_alt[0, sep_idx + 1] = 0  # logits score token 0 highly → low CE

        loss_alt = compute_masked_loss(logits, token_ids_alt)

        assert abs(loss_original.item() - loss_alt.item()) > 1e-3, (
            f"Changing first response token target must change loss — proves j=sep_pos is INCLUDED. "
            f"Original={loss_original.item():.6f}, Alt={loss_alt.item():.6f}"
        )
        # Also verify direction: loss_original > loss_alt (wrong prediction → higher loss)
        assert loss_original.item() > loss_alt.item(), (
            "With logits pointing to token 0, loss targeting token 50 should be > loss targeting token 0"
        )

    def test_loss_mask_handles_variable_sep_position(self):
        """Batch of 2 with different SEP positions → finite scalar loss, no shape errors."""
        T, V = 16, 256
        token_ids = torch.zeros(2, T, dtype=torch.long)
        # Sample 0: SEP at position 5
        token_ids[0, 5] = SEP
        token_ids[0, T - 1] = EOS
        # Sample 1: SEP at position 9
        token_ids[1, 9] = SEP
        token_ids[1, T - 1] = EOS

        logits = torch.randn(2, T, V)
        loss = compute_masked_loss(logits, token_ids)

        assert torch.isfinite(loss), f"Expected finite loss, got {loss.item()}"
        assert loss.ndim == 0, f"Expected scalar, got shape {loss.shape}"

    def test_loss_mask_returns_scalar_tensor(self):
        """Return type is torch.Tensor, ndim==0, and gradient flows when inputs require_grad."""
        T, V = 12, 256
        sep_idx = 4
        token_ids = torch.zeros(1, T, dtype=torch.long)
        token_ids[0, sep_idx] = SEP
        token_ids[0, T - 1] = EOS

        logits = torch.randn(1, T, V, requires_grad=True)
        loss = compute_masked_loss(logits, token_ids)

        assert isinstance(loss, torch.Tensor), f"Expected Tensor, got {type(loss)}"
        assert loss.ndim == 0, f"Expected scalar (ndim=0), got ndim={loss.ndim}"
        assert loss.requires_grad, "Loss should propagate gradients from logits"


# ---------------------------------------------------------------------------
# METRICS TESTS (TRAIN-04 prep)
# ---------------------------------------------------------------------------


class TestMetrics:
    def test_token_category_boundaries(self):
        """Verify all category boundary transitions."""
        ids = torch.tensor([0, 31, 32, 68, 69, 84, 85, 108, 109, 111, 112, 255])
        expected = torch.tensor([0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5])
        cats = token_category(ids)
        assert torch.equal(cats, expected), (
            f"token_category mismatch.\nExpected: {expected.tolist()}\nGot:      {cats.tolist()}"
        )

    def test_type_accuracy_perfect(self):
        """Perfect next-token predictions → type accuracy = 1.0."""
        T, V = 12, 256
        sep_idx = 4
        token_ids = torch.zeros(2, T, dtype=torch.long)
        # Build distinct response tokens in predictable categories
        for b in range(2):
            token_ids[b, sep_idx] = SEP
            for j in range(sep_idx + 1, T - 1):
                token_ids[b, j] = 32 + (j % 37)  # pitch range
            token_ids[b, T - 1] = EOS

        # Build logits where argmax == token_ids[:, j] (exact next-token prediction)
        logits = torch.full((2, T, V), -10.0)
        for b in range(2):
            for j in range(T - 1):
                target = token_ids[b, j + 1].item()
                logits[b, j, target] = 10.0

        acc = compute_type_accuracy(logits, token_ids)
        assert abs(acc - 1.0) < 1e-5, f"Expected type accuracy ~1.0, got {acc}"

    def test_type_accuracy_response_only(self):
        """Perfect on call side, wrong on response side → accuracy ≈ 0.0."""
        T, V = 12, 256
        sep_idx = 4
        token_ids = torch.zeros(2, T, dtype=torch.long)
        for b in range(2):
            token_ids[b, sep_idx] = SEP
            # Response tokens: pitch range [32..68]
            for j in range(sep_idx + 1, T - 1):
                token_ids[b, j] = 32 + (j % 37)
            token_ids[b, T - 1] = EOS

        # Logits: correct predictions on call side, wrong category on response side
        # Call side is irrelevant to metric; response side we predict time tokens (cat 0)
        # when targets are pitch tokens (cat 1)
        logits = torch.full((2, T, V), -10.0)
        for b in range(2):
            for j in range(T - 1):
                if j < sep_idx:
                    # Correct on call side (excluded from metric)
                    target = token_ids[b, j + 1].item()
                    logits[b, j, target] = 10.0
                else:
                    # Wrong: predict time-shift tokens (cat 0) when targets are pitch (cat 1)
                    # Ensure predicted token is in category 0 (time_shift: [0..31])
                    logits[b, j, 0] = 10.0  # argmax = 0, cat = 0 (time)

        acc = compute_type_accuracy(logits, token_ids)
        # All response predictions land in cat 0; targets are cat 1 → all wrong
        assert acc < 0.05, f"Expected type accuracy ≈ 0.0 (response-only), got {acc}"


# ---------------------------------------------------------------------------
# TRAIN STEP TESTS (TRAIN-03, TRAIN-05)
# ---------------------------------------------------------------------------


class TestTrainStep:
    def test_train_step_runs_cpu(self, train_dataloader):
        """Single train_epoch on CPU returns a finite float."""
        device = torch.device("cpu")
        model = ApolloModel().to(device)
        optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
        mean_loss = train_epoch(model, train_dataloader, optimizer, device)
        assert isinstance(mean_loss, float), f"Expected float, got {type(mean_loss)}"
        assert 0.0 <= mean_loss < 1e9, f"Expected finite positive loss, got {mean_loss}"

    def test_train_step_runs_on_mps(self, train_dataloader):
        """Single train_epoch on MPS executes without error."""
        if not torch.backends.mps.is_available():
            pytest.skip("MPS not available on this machine")
        device = torch.device("mps")
        model = ApolloModel().to(device)
        optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
        mean_loss = train_epoch(model, train_dataloader, optimizer, device)
        assert isinstance(mean_loss, float), f"Expected float, got {type(mean_loss)}"
        assert torch.tensor(mean_loss).isfinite(), f"Expected finite loss, got {mean_loss}"
        # At least one model parameter should be on MPS
        mps_params = [p for p in model.parameters() if p.device.type == "mps"]
        assert len(mps_params) > 0, "Expected model parameters on MPS device"

    def test_random_init_no_checkpoint_load(self):
        """Two differently-seeded ApolloModel inits produce different params (random init check).
        Also verifies train.py contains no load_state_dict call.
        """
        torch.manual_seed(42)
        model_a = ApolloModel()
        params_a = model_a.state_dict()["tok_emb.weight"].clone()

        torch.manual_seed(9999)
        model_b = ApolloModel()
        params_b = model_b.state_dict()["tok_emb.weight"].clone()

        assert not torch.equal(params_a, params_b), (
            "Two ApolloModel instances with different seeds should have different parameters"
        )

        # Verify no load_state_dict in train.py (TRAIN-03)
        train_src = open("apollo/model/train.py").read()
        assert "load_state_dict(" not in train_src, (
            "apollo/model/train.py must NOT contain load_state_dict() — TRAIN-03 prohibits warm-start"
        )

    def test_mel_encoder_params_update(self, train_dataloader):
        """mel_enc parameters must change after one train_epoch (jointly trained, COND-03 / D-02)."""
        device = torch.device("cpu")
        model = ApolloModel().to(device)
        optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)

        # Snapshot mel_enc fc weight before training
        before = model.mel_enc.fc.weight.detach().clone()

        train_epoch(model, train_dataloader, optimizer, device)

        after = model.mel_enc.fc.weight.detach().clone()
        assert not torch.equal(before, after), (
            "mel_enc.fc.weight should change after train_epoch — mel encoder must be jointly trained"
        )

    def test_response_loss_lower_than_call_loss(self, mock_artifact):
        """After 30 epochs on the same mock data, response-side CE < call-side CE.

        This is the mask-direction verification: gradient must flow to response tokens,
        driving response CE down. Call side receives no gradient, so call CE stays high.
        """
        device = torch.device("cpu")
        model = ApolloModel()

        dataset = ApolloDataset(mock_artifact, split="all")
        dataloader = DataLoader(dataset, batch_size=2, collate_fn=collate_fn, shuffle=False)

        from apollo.model.train import run_training
        run_training(model, dataloader, n_epochs=30, lr=1e-3, device=device)

        # Evaluate on same data
        model.eval()
        call_losses = []
        resp_losses = []

        with torch.no_grad():
            for token_ids, pad_mask, mel in dataloader:
                token_ids = token_ids.to(device)
                pad_mask = pad_mask.to(device)
                mel = mel.to(device).float()

                logits = model(token_ids, mel, key_padding_mask=pad_mask)  # (B, T, V)
                B, T, V = logits.shape

                # Shifted: logits[:, :-1] predicts token_ids[:, 1:]
                logits_s = logits[:, :-1]      # (B, T-1, V)
                targets_s = token_ids[:, 1:]   # (B, T-1)

                sep_pos = (token_ids == SEP).long().argmax(dim=1)   # (B,)
                j_range = torch.arange(T - 1).unsqueeze(0)          # (1, T-1)

                resp_mask = (j_range >= sep_pos.unsqueeze(1))        # (B, T-1)
                call_mask = (j_range < sep_pos.unsqueeze(1))         # (B, T-1)

                per_token_loss = F.cross_entropy(
                    logits_s.reshape(-1, V),
                    targets_s.reshape(-1),
                    reduction="none",
                ).reshape(B, T - 1)

                resp_sum = (per_token_loss * resp_mask.float()).sum()
                call_sum = (per_token_loss * call_mask.float()).sum()
                resp_count = resp_mask.float().sum()
                call_count = call_mask.float().sum()

                if resp_count > 0:
                    resp_losses.append((resp_sum / resp_count).item())
                if call_count > 0:
                    call_losses.append((call_sum / call_count).item())

        resp_ce = sum(resp_losses) / len(resp_losses)
        call_ce = sum(call_losses) / len(call_losses)

        assert resp_ce < call_ce, (
            f"After 30 epochs, response CE ({resp_ce:.4f}) should be strictly less than "
            f"call CE ({call_ce:.4f}). If not, the loss mask is not directing gradient correctly."
        )

    def test_no_torch_compile(self):
        """train.py must not contain torch.compile (RESEARCH §4: does not work on MPS in PyTorch 2.8)."""
        train_src = open("apollo/model/train.py").read()
        assert "torch.compile" not in train_src, (
            "apollo/model/train.py must NOT contain torch.compile — RESEARCH §4: not supported on MPS (PyTorch 2.8)"
        )

    def test_get_device_returns_mps_if_available(self):
        """get_device() returns a torch.device with type in {mps, cpu}."""
        d = get_device()
        assert isinstance(d, torch.device), f"Expected torch.device, got {type(d)}"
        assert d.type in {"mps", "cpu"}, f"Expected mps or cpu, got {d.type}"
