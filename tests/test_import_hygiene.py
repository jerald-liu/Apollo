"""Regression tests for cross-package import hygiene.

`apollo.tokenizer` and `apollo.ingest` historically had a circular import:
`apollo.tokenizer.encoder` eagerly imported `apollo.ingest.errors.IngestError`,
which triggered `apollo.ingest.__init__` → `artifact.py` → back into
`apollo.tokenizer` while still partially initialized. The bug was masked when
the full pytest suite ran because `tests/test_error_handling.py` (alphabetically
first) primed `apollo.ingest` in `sys.modules` before any tokenizer test loaded.

We test in a clean subprocess so cached imports from other tests cannot hide
a recurrence.
"""

from __future__ import annotations

import subprocess
import sys


def _run(stmt: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", stmt],
        capture_output=True,
        text=True,
    )


def test_tokenizer_imports_standalone() -> None:
    """`from apollo.tokenizer import ...` must succeed without ingest being imported first."""
    result = _run("from apollo.tokenizer import Vocab, Note, Tokenizer; print(Vocab.VOCAB_SIZE)")
    assert result.returncode == 0, (
        f"apollo.tokenizer standalone import failed:\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    assert result.stdout.strip() == "256", result.stdout


def test_ingest_imports_standalone() -> None:
    """`from apollo.ingest import ...` must succeed without tokenizer being imported first."""
    result = _run(
        "from apollo.ingest import IngestError, ingest, save_artifact, MelExtractor; "
        "print('OK')"
    )
    assert result.returncode == 0, (
        f"apollo.ingest standalone import failed:\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    assert result.stdout.strip() == "OK"


def test_encoder_note_legacy_import() -> None:
    """Legacy `from apollo.tokenizer.encoder import Note` keeps working after the
    Note dataclass was hoisted into apollo.tokenizer.types."""
    result = _run(
        "from apollo.tokenizer.encoder import Note; "
        "n = Note(60, 64, 0.0, 0.5); "
        "print(n.pitch)"
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "60"
