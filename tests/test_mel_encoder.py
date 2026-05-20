"""
Contract tests for MelEncoder (COND-02, COND-03).

All six tests constitute the acceptance contract:
- shape on CPU and MPS
- parameter count (exactly 109,184)
- gradient flow (jointly-trained check, COND-03)
- d_model parametrization
- missing-channel-dim error
"""
import pytest
import torch
from apollo.model import MelEncoder


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_input(B: int = 4) -> torch.Tensor:
    """Return a batch of mel tensors with the channel dim: (B, 1, 96, 128)."""
    torch.manual_seed(0)
    return torch.randn(B, 1, 96, 128)


# ---------------------------------------------------------------------------
# Shape tests
# ---------------------------------------------------------------------------


def test_forward_shape_cpu():
    """MelEncoder(d_model=128) on (4, 1, 96, 128) returns (4, 128) float32 on CPU."""
    torch.manual_seed(0)
    model = MelEncoder(d_model=128)
    x = _make_input(B=4).to("cpu")
    out = model(x)
    assert out.shape == (4, 128), f"Expected (4, 128), got {out.shape}"
    assert out.dtype == torch.float32, f"Expected float32, got {out.dtype}"
    assert out.device.type == "cpu"


def test_forward_shape_mps():
    """MelEncoder on MPS returns (4, 128) with device.type == 'mps'."""
    if not torch.backends.mps.is_available():
        pytest.skip("MPS not available")
    torch.manual_seed(0)
    model = MelEncoder(d_model=128).to("mps")
    x = _make_input(B=4).to("mps")
    out = model(x)
    assert out.shape == (4, 128), f"Expected (4, 128), got {out.shape}"
    assert out.device.type == "mps"


# ---------------------------------------------------------------------------
# Parameter count test
# ---------------------------------------------------------------------------


def test_parameter_count():
    """MelEncoder(d_model=128) must have exactly 109,184 parameters."""
    model = MelEncoder(d_model=128)
    n_params = sum(p.numel() for p in model.parameters())
    assert n_params == 109_184, (
        f"Expected 109184 parameters, got {n_params}. "
        "Check the CNN architecture matches D-01."
    )


# ---------------------------------------------------------------------------
# Gradient-flow test (COND-03 — jointly-trained check)
# ---------------------------------------------------------------------------


def test_gradients_flow():
    """After a single backward pass every parameter must have a non-None, non-zero grad."""
    torch.manual_seed(0)
    model = MelEncoder(d_model=128)
    x = torch.randn(2, 1, 96, 128)  # no requires_grad on input (model params carry grad)
    out = model(x)
    loss = out.sum()
    loss.backward()

    for name, param in model.named_parameters():
        assert param.grad is not None, f"Parameter '{name}' has no gradient after backward"
        assert param.grad.abs().sum() > 0, (
            f"Parameter '{name}' has all-zero gradient after backward — "
            "gradient is not flowing through this parameter."
        )


# ---------------------------------------------------------------------------
# d_model parametrization test
# ---------------------------------------------------------------------------


def test_d_model_param_changes_output_dim():
    """MelEncoder(d_model=64) returns shape (B, 64)."""
    torch.manual_seed(0)
    model = MelEncoder(d_model=64)
    x = _make_input(B=3)
    out = model(x)
    assert out.shape == (3, 64), f"Expected (3, 64) for d_model=64, got {out.shape}"


# ---------------------------------------------------------------------------
# Error handling test
# ---------------------------------------------------------------------------


def test_no_channel_dim_raises():
    """Passing (B, 96, 128) (missing channel dim) must raise RuntimeError."""
    model = MelEncoder(d_model=128)
    x = torch.randn(2, 96, 128)  # 3D — Conv2d expects 4D
    with pytest.raises(RuntimeError):
        model(x)
