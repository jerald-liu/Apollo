# Apollo v1 Corpus Authoring Conventions

This directory holds hand-authored Ableton Operator call/response pairs that train the Apollo v1 model. Read this before authoring any pair.

## Minimum corpus size

At least **30 pairs** must exist in this directory before the first real training run (`apollo/scripts/train.py`). This is requirement **DATA-05**.

## Per-pair file layout (DATA-02)

Each pair lives at `data/pairs/NNN/` with exactly three files:

- `call.mid` — MIDI of the call phrase (one Operator MIDI track)
- `call.wav` — Manual Ableton bounce of `call.mid` through its Operator preset
- `response.mid` — MIDI of the response phrase (one Operator MIDI track)

`NNN` is zero-padded sequential (`001`, `002`, ..., `030`, ...).

## Authoring conventions (locked decisions)

| Convention | Value | Source |
|---|---|---|
| Tempo | **120 BPM** exactly. The ingest pipeline enforces ±2 BPM tolerance (`apollo/ingest/midi.py` `load_notes`). | D-01 |
| Operator preset | **Vary across pairs** — bright plucks, soft pads, percussive FM tones, etc. The model must learn that the right response depends on timbre. | D-02 |
| Key / scale | **Free choice per pair.** The tokenizer uses absolute pitch bins, so key variety is not a structural problem. | D-03 |
| Gesture length | **0.5–1.5 seconds, 2–6 notes per side.** Fits within `max_seq_len=64`. | D-04 |
| Response relationship | **Varied per pair** — echo, contrast, continuation, complement. No labeling required. | D-05 |
| Call vs. response preset | **Same or different is free choice per pair.** No constraint. | D-06 |
| Pitch-shift augmentation | **Deferred.** Do not author pitch-shifted variants. | D-07 |

## Authoring workflow (Ableton)

1. Create two MIDI tracks in Ableton. Set both to an Operator preset (preset choice varies per pair, see D-02).
2. Record the **call** phrase on track 1 (2–6 notes, 0.5–1.5s, at 120 BPM).
3. Record the **response** phrase on track 2 (2–6 notes, 0.5–1.5s, at 120 BPM).
4. Solo track 1, **bounce to audio** → save the resulting wav as `call.wav` inside `data/pairs/NNN/`.
5. Export the call MIDI clip as `call.mid` inside `data/pairs/NNN/`.
6. Export the response MIDI clip as `response.mid` inside `data/pairs/NNN/`.
7. Verify: `data/pairs/NNN/` now contains exactly `call.mid`, `call.wav`, `response.mid`.

## Validation

The ingest pipeline (`apollo/scripts/ingest_corpus.py`) will fail loudly on any non-conforming pair:

- Missing files → `IngestError` reports the offending pair
- Tempo outside 120 ± 2 BPM → `IngestError`
- Empty MIDI (zero notes) → `IngestError`
- Polyphony (overlapping notes on same track) → `IngestError`

Run `venv/bin/python -m apollo.scripts.ingest_corpus data/pairs/` to validate the corpus after authoring.
