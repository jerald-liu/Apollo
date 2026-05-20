---
phase: 02-model-training
reviewed: 2026-05-19T00:00:00Z
depth: standard
files_reviewed: 13
files_reviewed_list:
  - apollo/model/__init__.py
  - apollo/model/mel_encoder.py
  - apollo/model/metrics.py
  - apollo/model/packer.py
  - apollo/model/train.py
  - apollo/model/transformer.py
  - apollo/scripts/train_smoke.py
  - tests/test_checkpoint.py
  - tests/test_mel_encoder.py
  - tests/test_packer.py
  - tests/test_smoke_train.py
  - tests/test_train.py
  - tests/test_transformer.py
findings:
  critical: 0
  warning: 2
  info: 5
  total: 7
status: issues_found
---

# Phase 02: Code Review Report

**Reviewed:** 2026-05-19
**Depth:** standard
**Files Reviewed:** 13
**Status:** issues_found

## Summary

The Phase 2 model and training code is well-structured and carefully documented. The architecture decisions (decoder-only via `TransformerEncoderLayer` + causal mask, MEL prefix injection, response-only loss, length-based pad mask) are all correctly implemented. The known research pitfalls are addressed with explicit comments and tests that pin the exact boundary conditions.

Two warnings stand out: a latent `AttributeError` in `save_checkpoint` due to an overly broad type annotation, and a silent incorrect-loss path in both `compute_masked_loss` and `compute_type_accuracy` when a sequence contains no SEP token. Five info-level issues cover minor inconsistencies in magic numbers, file-handle hygiene, and test arithmetic.

No critical issues found.

## Warnings

### WR-01: `save_checkpoint` accesses `model.mel_enc` through an `nn.Module` signature

**File:** `apollo/model/train.py:155-180`

**Issue:** The function signature declares `model: nn.Module`, but the body unconditionally accesses `model.mel_enc.state_dict()` on line 174. Any caller that passes a non-`ApolloModel` module (e.g., a wrapped or subclassed model) will receive an `AttributeError` with no useful message at the call site. This is a latent bug that will surface during Phase 3 if the model ever gets wrapped (e.g., for gradient checkpointing or multi-device).

**Fix:**
```python
from apollo.model.transformer import ApolloModel  # or use a Protocol/typing.cast

def save_checkpoint(
    model: ApolloModel,   # tighten the annotation to ApolloModel
    vocab_dict: dict,
    model_config: dict,
    training_meta: dict,
    out_path: str,
) -> None:
    ...
    "mel_encoder_state_dict": model.mel_enc.state_dict(),
```

Alternatively, add a runtime guard:
```python
if not hasattr(model, "mel_enc"):
    raise TypeError(
        f"save_checkpoint requires an ApolloModel with a .mel_enc submodule, "
        f"got {type(model).__name__}"
    )
```

---

### WR-02: Silent incorrect behavior when SEP token is absent from a sequence

**File:** `apollo/model/train.py:72` and `apollo/model/metrics.py:43`

**Issue:** Both `compute_masked_loss` and `compute_type_accuracy` locate the SEP position via:
```python
sep_pos = (token_ids == sep_id).long().argmax(dim=1)
```
`argmax` on an all-zero tensor returns index 0. If any sequence in a batch lacks a SEP token (e.g., a malformed or truncated input), `sep_pos` becomes 0 and `loss_mask = j_range >= 0` becomes `True` for **all positions** — including BOS and call tokens. This silently corrupts the response-only loss guarantee with no error raised. The collate_fn guarantees SEP is always present when called correctly, but the functions themselves offer no defense against misuse.

**Fix:** Add an assertion before computing `sep_pos` in both functions:
```python
# In compute_masked_loss and compute_type_accuracy:
assert (token_ids == sep_id).any(dim=1).all(), (
    "All sequences in the batch must contain a SEP token; "
    "found at least one sequence without SEP — check collate_fn output."
)
sep_pos = (token_ids == sep_id).long().argmax(dim=1)
```

## Info

### IN-01: `metrics.py` hardcodes `sep_id=111` instead of importing the `SEP` constant

**File:** `apollo/model/metrics.py:30`

**Issue:** The `compute_type_accuracy` default parameter `sep_id: int = 111` duplicates the `SEP` constant defined in `apollo/model/packer.py`. `train.py` correctly imports `SEP` from packer; `metrics.py` does not. If the SEP token ID ever changes (e.g., a vocab restructure), `metrics.py` will silently use the stale value while everything else updates.

**Fix:**
```python
from apollo.model.packer import SEP as _SEP

def compute_type_accuracy(
    logits: torch.Tensor,
    token_ids: torch.Tensor,
    sep_id: int = _SEP,   # was: sep_id: int = 111
) -> float:
```

---

### IN-02: `train_smoke.py` computes `datetime.now()` twice, producing a skewed filename/metadata timestamp

**File:** `apollo/scripts/train_smoke.py:131,139`

**Issue:** The checkpoint filename timestamp (line 131) and the `training_meta["timestamp"]` value (line 139) are computed from two separate `datetime.now(timezone.utc)` calls separated by the `save_checkpoint` call. On a slow filesystem the two values will differ by a non-trivial amount, meaning the `training_meta` timestamp stored inside the file does not match the filename. This is not a correctness bug for the model but produces confusing artifacts.

**Fix:**
```python
timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
out_path = Path(out_dir) / f"smoke-{timestamp}.pt"

meta_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
training_meta = {
    ...
    "timestamp": meta_timestamp,
}
```
Or capture a single `now` before both uses:
```python
now = datetime.now(timezone.utc)
timestamp_file = now.strftime("%Y%m%dT%H%M%SZ")
timestamp_meta = now.strftime("%Y-%m-%dT%H:%M:%SZ")
```

---

### IN-03: `test_train.py` opens source files without a context manager

**File:** `tests/test_train.py:344` and `tests/test_train.py:430`

**Issue:** Two tests read source files with:
```python
train_src = open("apollo/model/train.py").read()
```
The file handle is never explicitly closed. Python's garbage collector will close it eventually, but this pattern holds the handle open for the GC cycle and is inconsistent with the `with`-statement best practice required in the rest of the codebase.

**Fix:**
```python
with open("apollo/model/train.py") as f:
    train_src = f.read()
```

---

### IN-04: `test_train.py` `test_response_loss_lower_than_call_loss` uses averaging-of-averages with potentially uneven batches

**File:** `tests/test_train.py:420-421`

**Issue:** The test accumulates per-batch mean losses and then averages them:
```python
resp_ce = sum(resp_losses) / len(resp_losses)
call_ce = sum(call_losses) / len(call_losses)
```
The mock artifact has 7 pairs evaluated with `batch_size=2`, producing three batches of 2 and one batch of 1. Averaging the four batch-level means weights the singleton batch equally with the full batches, which is not the true mean over all tokens. The assertion still holds in practice because the direction (resp < call) is robust, but the statistic is imprecise.

**Fix:** Accumulate weighted numerators and denominators (already done correctly in `_evaluate_type_accuracy` in `train_smoke.py`):
```python
resp_ce = sum(resp_losses) / max(resp_count_total, 1e-8)
call_ce = sum(call_losses) / max(call_count_total, 1e-8)
```

---

### IN-05: `test_packer.py` over-long sequence test has an inaccurate inline comment

**File:** `tests/test_packer.py:203-204`

**Issue:** The comment reads: `"# call_tokens of length 60 → packed = 1 (BOS) + 60 + 1 (SEP) + 1 (resp) + 1 (EOS) = 64"` then `"# Add one more response token to go over: 65 > 64"`. The actual packed length is `1 + 60 + 1 + 3 + 1 = 66`, not 65. The assertion is correct (66 > 64), but the comment misstates the calculation, making it harder to verify intent.

**Fix:**
```python
# call_tokens=60, resp_tokens=3 → packed = 1(BOS) + 60 + 1(SEP) + 3 + 1(EOS) = 66 > 64
call_toks = torch.zeros(60, dtype=torch.int32)
resp_toks = torch.zeros(3, dtype=torch.int32)
```

---

_Reviewed: 2026-05-19_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
