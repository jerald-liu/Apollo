# Spec: `src/model.py` — Generative Model

## Module purpose

A compound-event autoregressive Transformer with two conditioning pathways and
two output heads.

- **Inputs:** a token sequence, optional continuous spectral features,
  optional user embedding.
- **Outputs:** next-token logits over the 380-vocab space, plus continuous
  timbral descriptors (brightness, attack, richness, warmth, flux).

The model lives entirely on CPU or a single accelerator; it has no data
loading logic and performs no file I/O.

---

## `SpectralEncoder(spectral_dim=21, d_model=256)`

### `forward(spectral_features)` → `Tensor`

- **M1.1** Input shape: `(B, T, spectral_dim)`. Output shape: `(B, T, d_model)`.
- **M1.2** Works for any `B >= 1` and `T >= 1`.
- **M1.3** Output is a `torch.Tensor` on the same device as the input.
- **M1.4** Output contains only finite values for finite input.

---

## `TimbrePredictor(d_model=256, n_descriptors=5)`

### `forward(hidden)` → `Tensor`

- **M2.1** Input shape: `(B, T, d_model)`. Output shape: `(B, T, n_descriptors)`.
- **M2.2** Every output value lies in `[0.0, 1.0]` (final layer is sigmoid).
- **M2.3** Output is a `torch.Tensor` on the same device as the input.

---

## `ApolloModel` — construction

- **M3.1** Defaults yield a model with
  `vocab_size=380, d_model=256, nhead=4, num_layers=4, max_seq_len=1024`.
- **M3.2** When `spectral_dim > 0`, `self.spectral_encoder` is a
  `SpectralEncoder`; when `spectral_dim == 0`, it is `None`.
- **M3.3** When `n_timbre_outputs > 0`, `self.timbre_head` is a
  `TimbrePredictor`; when `0`, it is `None`.
- **M3.4** When `user_embed_dim > 0`, `self.user_proj` is a `nn.Linear`;
  when `0`, it is `None`.
- **M3.5** Parameter count for the default config is under 20 million.

---

## `ApolloModel.forward(tokens, spectral_features=None, user_embedding=None, tokens_per_event=5)` → `dict`

- **M4.1** `tokens` of shape `(B, T)` is required. `B >= 1`, `1 <= T <= max_seq_len`.
- **M4.2** Returns a `dict` that always contains `'logits'` of shape
  `(B, T, vocab_size)`.
- **M4.3** When `timbre_head` is not `None`, the dict also contains `'timbre'`
  of shape `(B, T, n_timbre_outputs)` with all values in `[0, 1]`.
- **M4.4** The call succeeds when `spectral_features is None` (the spectral
  path is skipped, not errored).
- **M4.5** The call succeeds when `user_embedding is None`.
- **M4.6** With `spectral_features` of shape `(B, N_events, spectral_dim)`
  where `N_events * tokens_per_event >= T`, the forward pass does not raise
  and output shape is unchanged.
- **M4.7** Output logits contain only finite values for finite input.
- **M4.8** Tokens at position `t` do not influence logits at position `< t`
  (causal masking — a prefix sanity check suffices: feeding `tokens[:, :t]`
  vs `tokens` produces the same logits over positions `[0, t-1]`).

---

## `ApolloModel._expand_spectral_to_tokens(spectral_features, tokens_per_event, total_tokens)` → `Tensor`

- **M5.1** For input of shape `(B, N, D)`, output has shape
  `(B, total_tokens, D)`.
- **M5.2** Each of the `N` event vectors is repeated `tokens_per_event` times
  along the time axis.
- **M5.3** When `N * tokens_per_event < total_tokens`, the tail is
  zero-padded.
- **M5.4** When `N * tokens_per_event > total_tokens`, the output is
  truncated to `total_tokens`.

---

## `ApolloModel.generate(prompt, max_new_tokens, temperature, top_k, ...)` → `Tuple[Tensor, Optional[Tensor]]`

- **M6.1** Returns `(tokens, timbre)` where `tokens` has shape `(1, T_out)` and
  `T_out <= prompt.shape[1] + max_new_tokens`.
- **M6.2** The first `prompt.shape[1]` tokens of the output equal `prompt`.
- **M6.3** Every generated token lies in `[0, vocab_size - 1]`.
- **M6.4** Generation halts early when the EOS token (378) is sampled.
- **M6.5** When `timbre_head` is not `None`, `timbre` is a `Tensor` of shape
  `(1, N_new, n_timbre_outputs)` with `N_new` = number of generation steps
  actually taken.
- **M6.6** When `timbre_head is None`, the second return value is `None`.
- **M6.7** Runs under `torch.no_grad()` — gradients are not tracked and the
  model is in eval mode during the call.
