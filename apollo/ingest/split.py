"""Deterministic hash-based held-out split.

See .planning/phases/01-tokenizer-ingest/01-RESEARCH.md §"Deterministic Split"
and CONTEXT.md D-20. A pair NNN is held out iff
`int(sha1(nnn).hexdigest(), 16) % 5 == 0`, giving an expected 20% split.

Determinism guarantees (per RESEARCH.md):
- sha1 is deterministic across Python versions, platforms, and time.
- Adding a new pair never changes the split assignment of existing pairs.
- Renaming a pair (e.g. `001/` → `031/`) DOES change its split — that's
  the right behavior because the folder name IS the identity key.
"""

from __future__ import annotations

import hashlib


def normalize_nnn(nnn: str) -> str:
    """Canonical form for NNN strings before hashing.

    Strips whitespace, lowercases (no-op for digit folders but defensive),
    and preserves any zero-padding (`001` stays `001`, not `1`). Raises
    `ValueError` on empty input — an empty NNN cannot be a valid pair key.
    """
    s = nnn.strip().lower()
    if not s:
        raise ValueError("empty NNN string")
    return s


def is_heldout(nnn: str, k: int = 5) -> bool:
    """Return True if pair `nnn` is in the held-out (eval) split.

    `k=5` gives a 20% split. Stable across runs; immune to authoring order.
    """
    s = normalize_nnn(nnn)
    h = int(hashlib.sha1(s.encode("utf-8")).hexdigest(), 16)
    return (h % k) == 0
