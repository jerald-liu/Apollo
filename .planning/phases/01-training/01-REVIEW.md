---
phase: 01-training
reviewed: 2026-05-14T00:00:00Z
depth: standard
files_reviewed: 2
files_reviewed_list:
  - modal_train.py
  - Makefile
findings:
  critical: 0
  warning: 3
  info: 3
  total: 6
status: issues_found
---

# Phase 1: Code Review Report

**Reviewed:** 2026-05-14
**Depth:** standard
**Files Reviewed:** 2
**Status:** issues_found

## Summary

Reviewed `modal_train.py` and `Makefile` for the Phase 1 per-run checkpoint subdirectory patch. The core change — routing checkpoints to `/checkpoints/{run_name}/` and updating `pull-checkpoints` to match — is correct and coherent. No critical (security or data-loss) issues were found.

Three warnings were identified: a stale resume path in the module docstring, a subprocess import duplication that could cause confusion, and a silent failure in `pull-checkpoints` that suppresses errors for all failures (not just missing files). Three info-level items cover a missing `ckpt_vol.commit()` guard on training failure, a missing `data_vol.commit()` guard on preprocessing failure, and a stale usage example in the docstring.

---

## Warnings

### WR-01: Resume path in docstring is stale — points to volume root, not per-run subdir

**File:** `modal_train.py:17`
**Issue:** The docstring instructs users to resume with `--resume checkpoint_latest.pt`. After the patch, `train()` resolves resume paths as `{CKPT_DIR}/{run_name}/{resume}`. A bare filename like `checkpoint_latest.pt` is correct _only if_ the caller already strips the subdir component. The docstring gives no indication that the argument must be a bare filename (not a path), making it ambiguous. If a user passes the old-style path `apollo_v3_mel/checkpoint_latest.pt` the resolved path becomes `/checkpoints/apollo_v3_mel/apollo_v3_mel/checkpoint_latest.pt` and training fails silently with a missing checkpoint error from the underlying `train.py` script.

**Fix:** Update the docstring usage example to clarify the argument is a bare filename, and add a guard in `train()` to strip any leading directory component:
```python
# In train(), after computing _run_ckpt_dir:
if resume:
    resume_file = Path(resume).name   # strip any accidental path prefix
    args += ["--resume", f"{_run_ckpt_dir}/{resume_file}"]
```
And update the docstring:
```
# Resume an interrupted run (bare filename only — subdir is added automatically)
modal run modal_train.py --resume checkpoint_latest.pt
```

---

### WR-02: Duplicate `subprocess` import inside `train()` — shadowing risk

**File:** `modal_train.py:148`
**Issue:** `train()` imports `subprocess` at the top of the function body (`import subprocess, yaml as _yaml`) and then imports it again as `_sp` two lines later (`import subprocess as _sp`). The final `subprocess.run(args, ...)` call on line 174 uses the first binding. This is not a runtime bug today, but the two bindings refer to the same module object. The `_sp` alias is used only for `mkdir -p` (line 163) while the bare `subprocess` is used for the main training call (line 174). If a future edit removes one import without noticing the other, or swaps which name is used, behavior diverges unexpectedly.

**Fix:** Use a single consistent import:
```python
def train(config: str = "configs/base.yaml", resume: str = None):
    import subprocess
    import yaml as _yaml
    ...
    subprocess.run(["mkdir", "-p", _run_ckpt_dir], check=True)
    ...
    subprocess.run(args, cwd="/workspace", check=True)
```

---

### WR-03: `pull-checkpoints` silences all errors, not just missing-file errors

**File:** `Makefile:71-74`
**Issue:** Each `modal volume get` line redirects stderr to `/dev/null` and appends `|| true`, meaning any error — wrong volume name, authentication failure, network timeout, Modal CLI crash — is silently swallowed and the target always exits 0. This makes `make pull-checkpoints` appear to succeed even when nothing was downloaded. The `ls` summary at line 76 partially mitigates this, but only shows files already present in `models/`, not whether the download actually ran.

**Fix:** Remove `2>/dev/null` so errors surface in terminal output. Keep `|| true` only if you intentionally want to tolerate absent checkpoints (which is reasonable here since v3/v4 runs may not both be complete). The combined form that keeps missing-file tolerance while surfacing real errors:
```makefile
$(MODAL) volume get apollo-checkpoints apollo_v3_mel/checkpoint_best.pt    models/checkpoint_v3_best.pt    || true
$(MODAL) volume get apollo-checkpoints apollo_v3_mel/checkpoint_latest.pt  models/checkpoint_v3_latest.pt  || true
$(MODAL) volume get apollo-checkpoints apollo_v4_streaming/checkpoint_best.pt    models/checkpoint_v4_best.pt    || true
$(MODAL) volume get apollo-checkpoints apollo_v4_streaming/checkpoint_latest.pt  models/checkpoint_v4_latest.pt  || true
```

---

## Info

### IN-01: `ckpt_vol.commit()` not called on training failure path

**File:** `modal_train.py:175`
**Issue:** `ckpt_vol.commit()` is called only after a successful `subprocess.run(..., check=True)` completes. If `train.py` writes intermediate checkpoints during a long run and then crashes (e.g., OOM on the last step), those writes are not committed to the Modal volume before the container exits. Modal volumes auto-persist eventually, but explicit `commit()` is the recommended pattern to guarantee durability. A `try/finally` would protect partial progress.

**Fix:**
```python
try:
    subprocess.run(args, cwd="/workspace", check=True)
finally:
    ckpt_vol.commit()
```

---

### IN-02: `data_vol.commit()` not called on preprocessing failure path

**File:** `modal_train.py:130`
**Issue:** Same pattern as IN-01. `data_vol.commit()` is only called after the preprocessor exits cleanly. Partial preprocessing output (e.g., some `.pt` shard files written before a crash) would not be explicitly committed.

**Fix:**
```python
try:
    subprocess.run(args, cwd="/workspace", check=True)
finally:
    data_vol.commit()
```

---

### IN-03: Module docstring checkpoint download example is stale

**File:** `modal_train.py:22-23`
**Issue:** The "Download best checkpoint after training" example uses the volume root path (`checkpoint_best.pt`) rather than the new per-run subdir path (`apollo_v3_mel/checkpoint_best.pt`). Running the command as written would fail with a file-not-found error.

**Fix:** Update the docstring to reflect the new layout:
```
# Download best checkpoint after training
modal volume get apollo-checkpoints apollo_v3_mel/checkpoint_best.pt models/checkpoint_v3_best.pt
modal volume get apollo-checkpoints apollo_v4_streaming/checkpoint_best.pt models/checkpoint_v4_best.pt
```

---

_Reviewed: 2026-05-14_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
