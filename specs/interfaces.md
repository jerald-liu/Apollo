# Spec: Interface Contracts Between Components

Interface contracts define the **boundary conditions** that must hold where one
module's output becomes another module's input. Each clause is named `I<from>→<to>.<n>`.

A violation here means the pipeline is broken at a seam, regardless of whether
each module passes its own unit tests.

---

## I:R→M — `representation` → `model`

The token sequence produced by `events_to_tokens` is what `ApolloModel.forward`
receives as `tokens`.

- **IR→M.1** Every token `t` from `events_to_tokens` satisfies `0 <= t < VOCAB_SIZE` (380).
  `ApolloModel` embeds tokens via `nn.Embedding(vocab_size=380, ...)` — an
  out-of-range token raises an index error at runtime.
- **IR→M.2** `events_to_continuous` returns shape `(N, CONTINUOUS_DIM)` where
  `CONTINUOUS_DIM == 21`. `SpectralEncoder` is constructed with `spectral_dim=21`.
  If either constant changes independently, the projection layer silently produces
  wrong-shaped output or raises.
- **IR→M.3** The number of events `N` and the token count `T` satisfy
  `T == 2 + N * TOKENS_PER_EVENT` (MIDI-only mode). `_expand_spectral_to_tokens`
  uses `tokens_per_event=TOKENS_PER_EVENT` to align spectral features to tokens.
  A mismatch misaligns every spectral embedding by a fixed offset.
- **IR→M.4** The BOS token (`377`) appears only at position 0 and the EOS token
  (`378`) only at the final position. `generate` halts on token `378`; a BOS/EOS
  embedded mid-sequence would terminate generation prematurely.

---

## I:R→P — `representation` → `preprocess`

`process_file` calls `events_to_tokens` and passes the result to
`create_training_windows`.

- **IR→P.1** `process_file` returns `n_tokens == len(tokens)` — the count it
  stores matches the actual list length. `create_training_windows` uses
  `len(tokens)` directly; a stale count would produce wrong window boundaries.
- **IR→P.2** All tokens returned by `process_file` satisfy `0 <= t < VOCAB_SIZE`.
  `create_training_windows` stores them in `np.int32` arrays without range checks;
  an invalid token is silently stored and will cause an embedding error at training
  time.
- **IR→P.3** `create_training_windows` produces windows of shape `(N, seq_len+1)`
  in `np.int32`. The training loop indexes `window[:, :-1]` as input and
  `window[:, 1:]` as target; if `dtype` or the `+1` invariant breaks, targets are
  misaligned by one position.

---

## I:S→R — `spectral` → `representation`

`midi_to_events` optionally calls `SpectralAnalyzer` and maps its output onto
`ApolloEvent` timbral fields.

- **IS→R.1** `NoteSpectralProfile` fields `brightness, attack, richness, warmth,
  flux` are in `[0, 1]` after `normalize_profile`. `ApolloEvent` stores them as
  floats without clamping; values outside `[0, 1]` are passed directly into
  `events_to_continuous` and thence into the model, corrupting the spectral
  side-channel.
- **IS→R.2** `SpectralTrajectory.to_embedding(time, dim=TRAJECTORY_DIM)` returns
  shape `(TRAJECTORY_DIM,)` = `(16,)`. `ApolloEvent.trajectory` is declared as
  shape `(16,)`. A mismatch silently truncates or pads the trajectory stored on
  each event.
- **IS→R.3** `events_to_continuous` reads columns `[5:5+TRAJECTORY_DIM]` from
  the trajectory. `TRAJECTORY_DIM` must equal the `dim` argument passed to
  `to_embedding`. If they diverge, the continuous feature matrix has wrong
  semantics in its trailing columns.

---

## I:M→G — `model.forward` → `model.generate`

`generate` is a loop over `forward`; the output dict of `forward` is consumed
directly inside `generate`.

- **IM→G.1** `forward` always returns a dict containing `'logits'` of shape
  `(B, T, vocab_size)`. `generate` indexes `output['logits'][:, -1, :]`; a
  missing key or wrong shape raises `KeyError` or an index error mid-generation.
- **IM→G.2** When `timbre_head is not None`, `forward` returns `'timbre'` of
  shape `(B, T, n_timbre_outputs)`. `generate` appends `output['timbre'][:, -1, :]`
  at each step; if the key is absent or the slice is wrong-shaped,
  `torch.stack(timbre_preds)` produces a malformed tensor.
- **IM→G.3** The EOS token index used in `generate` (`== 378`) must equal
  `TOKEN_OFFSETS['eos']` from `representation`. If `eos` is renumbered in the
  vocabulary, `generate` never halts (or halts on the wrong token).
