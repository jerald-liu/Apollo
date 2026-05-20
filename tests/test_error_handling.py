"""Error-handling tests for the ingest pipeline.

Covers every documented error site from RESEARCH.md §"Error Handling / Call
sites": missing files, corrupted MIDI, symlink-escape mitigation, overlapping
notes, pitch out of range, and the CLI exit-code map (0 success, 1 IngestError,
2 unexpected).

Phase 01 Plan 05 — proves error paths abort with the offending pair identified
(not silently skip).
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from apollo.ingest import ingest, synthesize_pair, IngestError


def _build_root_with_one_pair(tmp_path, nnn="000"):
    root = tmp_path / "pairs"
    synthesize_pair(root, nnn=nnn)
    return root


def test_missing_call_wav_aborts(tmp_path):
    root = _build_root_with_one_pair(tmp_path)
    os.remove(root / "000" / "call.wav")
    with pytest.raises(IngestError) as exc:
        ingest(str(root))
    assert "call.wav" in exc.value.reason
    assert "000" in exc.value.pair_path


def test_missing_call_mid_aborts(tmp_path):
    root = _build_root_with_one_pair(tmp_path)
    os.remove(root / "000" / "call.mid")
    with pytest.raises(IngestError) as exc:
        ingest(str(root))
    assert "call.mid" in exc.value.reason


def test_missing_response_mid_aborts(tmp_path):
    root = _build_root_with_one_pair(tmp_path)
    os.remove(root / "000" / "response.mid")
    with pytest.raises(IngestError) as exc:
        ingest(str(root))
    assert "response.mid" in exc.value.reason


def test_corrupted_call_mid_aborts(tmp_path):
    root = _build_root_with_one_pair(tmp_path)
    (root / "000" / "call.mid").write_bytes(b"\x00\x01\x02not a midi file at all\xff")
    with pytest.raises(IngestError) as exc:
        ingest(str(root))
    assert "parse" in exc.value.reason or "failed" in exc.value.reason


def test_symlink_escape_aborts(tmp_path):
    # Create an external pair somewhere outside the intended corpus root
    outside = tmp_path / "elsewhere"
    synthesize_pair(outside, nnn="000")
    # The corpus root contains a symlink pointing OUT to the external pair
    root = tmp_path / "pairs"
    root.mkdir()
    (root / "000").symlink_to(outside / "000")
    with pytest.raises(IngestError) as exc:
        ingest(str(root))
    assert "path traversal" in exc.value.reason or "symlink" in exc.value.reason


def test_overlapping_notes_aborts(tmp_path):
    # Synthesize then overwrite call.mid with overlapping-note content
    root = _build_root_with_one_pair(tmp_path)
    import pretty_midi
    pm = pretty_midi.PrettyMIDI(initial_tempo=120.0)
    inst = pretty_midi.Instrument(program=0)
    # Two notes overlapping by 0.1 sec; onsets at 0.5 IOI keep estimate_tempo
    # at 120 bpm so the overlap check (not the tempo check) is the abort site.
    inst.notes.append(pretty_midi.Note(velocity=80, pitch=60, start=0.0, end=0.6))
    inst.notes.append(pretty_midi.Note(velocity=80, pitch=62, start=0.5, end=1.0))
    pm.instruments.append(inst)
    pm.write(str(root / "000" / "call.mid"))
    with pytest.raises(IngestError) as exc:
        ingest(str(root))
    assert "overlapping" in exc.value.reason


def test_pitch_out_of_range_aborts(tmp_path):
    # Build a pair whose call.mid has pitch=24 (below C2 / MIDI 36)
    root = tmp_path / "pairs"
    synthesize_pair(root, nnn="000", call_pitches=(24,), call_durs=(0.5,))
    with pytest.raises(IngestError) as exc:
        ingest(str(root))
    assert "outside" in exc.value.reason


def test_cli_exit_code_one_on_ingest_error(tmp_path):
    root = _build_root_with_one_pair(tmp_path)
    os.remove(root / "000" / "call.wav")
    result = subprocess.run(
        [sys.executable, "-m", "apollo.scripts.ingest_corpus", str(root),
         "--output", str(tmp_path / "out.pt")],
        capture_output=True, text=True,
    )
    assert result.returncode == 1, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "INGEST FAILED" in result.stderr
    assert "call.wav" in result.stderr


def test_cli_exit_code_zero_on_happy_path(tmp_path):
    root = tmp_path / "pairs"
    for i in range(3):
        synthesize_pair(root, nnn=f"{i:03d}")
    out = tmp_path / "out.pt"
    result = subprocess.run(
        [sys.executable, "-m", "apollo.scripts.ingest_corpus", str(root),
         "--output", str(out)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "OK: 3 pairs" in result.stdout
    assert out.is_file()
