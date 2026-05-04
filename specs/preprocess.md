# Spec: `scripts/preprocess.py` — Preprocessing Pipeline

## Module purpose

Converts a directory of MAESTRO MIDI files (optionally with paired audio) into
training-ready `.npy` arrays of fixed-length token windows, plus an optional
aligned continuous spectral feature tensor. Also writes a `meta.json`
summarizing the run.

This is the scripted integration point for `representation.py` and
`spectral.py`, so its contract is primarily about **shapes, value ranges, and
error resilience** rather than low-level tokenization semantics.

---

## `process_file(args)` → `Optional[dict]`

`args` is a 4-tuple `(midi_path, audio_path, use_spectral, max_events)`.

- **P1.1** Returns `None` when the file yields fewer than 10 events.
- **P1.2** Returns a dict with an `'error'` key (string) on any exception;
  never lets the exception propagate. This is required for multiprocessing
  robustness — one bad file must not kill the whole run.
- **P1.3** On success returns a dict with keys `tokens, continuous, n_events,
  n_tokens`.
- **P1.4** `n_tokens == len(tokens)`.
- **P1.5** `n_events >= 10`.
- **P1.6** When `use_spectral` is `False`, `continuous` is `None`.
- **P1.7** All returned tokens are valid (`0 <= t < VOCAB_SIZE`).

---

## `create_training_windows(all_tokens, all_continuous, seq_len, stride)` → `(np.ndarray, Optional[np.ndarray])`

- **P2.1** Returns `(token_arr, cont_arr)`. `token_arr` is always an `ndarray`.
- **P2.2** `token_arr.shape == (N, seq_len + 1)` where `N` is the number of
  windows produced. The extra `+1` supplies the autoregressive target.
- **P2.3** `token_arr.dtype == np.int32`.
- **P2.4** Every token value in `token_arr` is in `[0, VOCAB_SIZE - 1]`.
- **P2.5** For a single input sequence of length `L`, the number of windows
  produced equals `max(0, (L - seq_len + stride - 1) // stride)` (standard
  strided slicing with `range(0, L - seq_len, stride)`).
- **P2.6** When `all_continuous is None`, `cont_arr is None`.
- **P2.7** When `all_continuous` is provided, `cont_arr.dtype == np.float32`
  and `cont_arr.shape[0] == token_arr.shape[0]`.

---

## End-to-end (integration)

- **P3.1** Given a directory containing a single valid MIDI file with ≥ 10
  notes, `process_file` returns a dict with valid tokens and the subsequent
  `create_training_windows` call returns at least one window for any
  `seq_len < len(tokens)`.
- **P3.2** A directory containing one valid file and one corrupt file
  produces exactly one valid result and one `'error'` result.
