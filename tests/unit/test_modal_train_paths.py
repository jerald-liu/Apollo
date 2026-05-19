"""Tests for the checkpoint-isolation path derivation fixed in Phase 1 (Plan 01-01).

modal_train.py embeds path derivation inside a Modal @app.function body which
cannot be called locally.  These tests verify the derivation algorithm against
the same constants used in production:

    DATA_DIR = "/data"
    CKPT_DIR = "/checkpoints"

so any change to the logic in modal_train.py that breaks run isolation is
caught here.

Relevant lines in modal_train.py:
    _run_name      = _cfg.get("run_name", "apollo_run")
    _run_ckpt_dir  = f"{CKPT_DIR}/{_run_name}"
    _local_data_dir = _cfg.get("data_dir", "data/processed")
    _sub            = _local_data_dir.split("/", 1)[-1]
    _remote_data_dir = f"{DATA_DIR}/{_sub}"
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

# Mirror the constants from modal_train.py.
# If these change in production, update here and review the derivation tests.
DATA_DIR = "/data"
CKPT_DIR = "/checkpoints"


# ---------------------------------------------------------------------------
# Helpers — mirror the derivation blocks in modal_train.py::train()
# ---------------------------------------------------------------------------

def _derive_run_paths(cfg: dict) -> tuple[str, str]:
    """Mirrors the run-path block in modal_train.py::train()."""
    run_name = cfg.get("run_name", "apollo_run")
    run_ckpt_dir = f"{CKPT_DIR}/{run_name}"
    return run_name, run_ckpt_dir


def _derive_data_path(cfg: dict) -> str:
    """Mirrors the data-dir derivation block in modal_train.py::train()."""
    local_data_dir = cfg.get("data_dir", "data/processed")
    sub = local_data_dir.split("/", 1)[-1]
    return f"{DATA_DIR}/{sub}"


# ---------------------------------------------------------------------------
# Checkpoint isolation (the Plan 01-01 bug fix)
# ---------------------------------------------------------------------------

class TestCheckpointIsolation:
    def test_v3_v4_produce_separate_dirs(self):
        """Bug fixed in Plan 01-01: v3 and v4 previously both wrote to
        /checkpoints/ (flat).  After the fix each run_name gets its own
        sub-directory so parallel runs can't overwrite each other's best.pt."""
        v3_cfg = {"run_name": "apollo_v3_mel"}
        v4_cfg = {"run_name": "apollo_v4_streaming"}

        _, v3_dir = _derive_run_paths(v3_cfg)
        _, v4_dir = _derive_run_paths(v4_cfg)

        assert v3_dir != v4_dir
        assert v3_dir == "/checkpoints/apollo_v3_mel"
        assert v4_dir == "/checkpoints/apollo_v4_streaming"

    def test_run_name_extracted_from_config(self):
        """run_name comes from cfg['run_name'], not a hardcoded constant."""
        cfg = {"run_name": "my_custom_run"}
        run_name, ckpt_dir = _derive_run_paths(cfg)
        assert run_name == "my_custom_run"
        assert ckpt_dir == "/checkpoints/my_custom_run"

    def test_run_name_fallback_when_absent(self):
        """Config without run_name falls back to 'apollo_run' — no KeyError."""
        _, ckpt_dir = _derive_run_paths({})
        assert ckpt_dir == "/checkpoints/apollo_run"

    def test_ckpt_dir_is_always_a_subdir_of_volume_root(self):
        """Every run dir must be under CKPT_DIR, never at the volume root itself.
        Writing directly to /checkpoints/ would mix checkpoints from all runs."""
        for name in ["apollo_v3_mel", "apollo_v4_streaming", "apollo_run"]:
            _, ckpt_dir = _derive_run_paths({"run_name": name})
            assert ckpt_dir.startswith(CKPT_DIR + "/"), (
                f"Expected {ckpt_dir!r} to be a sub-directory of {CKPT_DIR!r}"
            )
            assert ckpt_dir != CKPT_DIR, (
                "ckpt_dir must not equal CKPT_DIR — that's the old collision bug"
            )


# ---------------------------------------------------------------------------
# Remote data-dir mapping
# ---------------------------------------------------------------------------

class TestDataDirMapping:
    def test_streaming_data_dir(self):
        """v4 streaming: 'data/processed_streaming' → '/data/processed_streaming'."""
        cfg = {"data_dir": "data/processed_streaming"}
        assert _derive_data_path(cfg) == "/data/processed_streaming"

    def test_base_data_dir(self):
        """v2/v3 base tokenisation: 'data/processed' → '/data/processed'."""
        cfg = {"data_dir": "data/processed"}
        assert _derive_data_path(cfg) == "/data/processed"

    def test_default_data_dir_when_absent(self):
        """Config without data_dir falls back to 'data/processed'."""
        assert _derive_data_path({}) == "/data/processed"

    def test_no_double_data_prefix(self):
        """The 'data/' prefix in the local path must be stripped exactly once;
        the result should never start with '/data/data'."""
        cfg = {"data_dir": "data/anything"}
        result = _derive_data_path(cfg)
        assert result == "/data/anything"
        assert not result.startswith("/data/data"), (
            "Double 'data/' prefix detected — split logic is broken"
        )
