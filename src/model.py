"""Apollo generative model — compound event Transformer with spectral conditioning.

Generates musical events conditioned on:
1. Token sequence (pitch, velocity, timing, duration, pedal)
2. Continuous spectral features (brightness, attack, richness, warmth, flux + trajectory)
3. Optional user embedding for personalization

Outputs:
1. Next-token logits (standard autoregressive)
2. Continuous timbral predictions (brightness, attack, richness, warmth, flux)
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import math
from typing import Optional, Dict, Tuple, List


class SpectralEncoder(nn.Module):
    """Projects continuous spectral features into the token embedding space.

    Takes per-event spectral features (5 note-level + 16 trajectory) and
    produces a vector that gets added to the token embeddings, giving the
    model access to timbral context at each position.
    """

    def __init__(self, spectral_dim: int = 21, d_model: int = 256):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(spectral_dim, d_model // 2),
            nn.GELU(),
            nn.Linear(d_model // 2, d_model),
            nn.LayerNorm(d_model),
        )

    def forward(self, spectral_features: torch.Tensor) -> torch.Tensor:
        """
        Args:
            spectral_features: (B, T_events, spectral_dim) continuous features

        Returns:
            (B, T_events, d_model) projected spectral embeddings
        """
        return self.net(spectral_features)


class MelEncoder(nn.Module):
    """Encodes a log-mel spectrogram patch into a single d_model context vector.

    Broadcasts over all token positions in the window — the entire window
    shares one mel embedding (coarse conditioning). Phase 3.2 will add
    multi-scale fine/mid/coarse branches.

    Input:  (B, mel_frames, n_mels)  e.g. (B, 256, 128)
    Output: (B, 1, d_model)          broadcast over T token positions
    """

    def __init__(self, n_mels: int = 128, d_model: int = 384):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv2d(1, 32, kernel_size=(3, 3), padding=1),
            nn.GELU(),
            nn.Conv2d(32, 64, kernel_size=(3, 3), padding=1),
            nn.GELU(),
            nn.AdaptiveAvgPool2d((8, 8)),   # → (B, 64, 8, 8)
        )
        self.proj = nn.Linear(64 * 8 * 8, d_model)
        self.norm = nn.LayerNorm(d_model)

    def forward(self, mel: torch.Tensor) -> torch.Tensor:
        """
        Args:
            mel: (B, mel_frames, n_mels)
        Returns:
            (B, 1, d_model)
        """
        x = mel.unsqueeze(1)          # (B, 1, mel_frames, n_mels)
        x = self.conv(x)              # (B, 64, 8, 8)
        x = x.flatten(1)              # (B, 4096)
        x = self.norm(self.proj(x))   # (B, d_model)
        return x.unsqueeze(1)         # (B, 1, d_model)


class TimbrePredictor(nn.Module):
    """Predicts continuous timbral descriptors from the model's hidden states.

    This is the output side: given the Transformer's representation at each
    position, predict what the *response* should sound like timbrally.
    """

    def __init__(self, d_model: int = 256, n_descriptors: int = 5):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(d_model, d_model // 2),
            nn.GELU(),
            nn.Linear(d_model // 2, n_descriptors),
            nn.Sigmoid(),  # output in [0, 1]
        )

    def forward(self, hidden: torch.Tensor) -> torch.Tensor:
        """
        Args:
            hidden: (B, T, d_model) Transformer hidden states

        Returns:
            (B, T, n_descriptors) predicted timbral values in [0, 1]
        """
        return self.net(hidden)


class CodecHead(nn.Module):
    """Predicts EnCodec RVQ tokens from transformer hidden states (Phase 4).

    EnCodec at 24kHz / 6kbps: 4 codebooks × 1024 tokens at 75 Hz.
    This head operates at MIDI-event resolution; a lightweight upsampler
    (trained jointly) maps event-level predictions to 75Hz codec frames
    during inference.

    Training: cross-entropy loss per codebook level against EnCodec tokens
    extracted from paired MAESTRO audio during preprocessing.
    """

    N_CODEBOOKS   = 4
    CODEBOOK_SIZE = 1024

    def __init__(self, d_model: int = 384):
        super().__init__()
        # One linear head per RVQ codebook level
        self.heads = nn.ModuleList([
            nn.Linear(d_model, self.CODEBOOK_SIZE)
            for _ in range(self.N_CODEBOOKS)
        ])
        # Lightweight 1-D conv upsampler: event-rate → 75 Hz codec rate
        # Configured at runtime based on actual event/codec rate ratio.
        # Set scale_factor when wiring into training (e.g. 75 / events_per_sec).
        self.upsampler = None  # initialised in train.py when codec rate is known

    def forward(self, hidden: torch.Tensor) -> list[torch.Tensor]:
        """
        Args:
            hidden: (B, T_events, d_model)
        Returns:
            list of N_CODEBOOKS tensors, each (B, T_events, CODEBOOK_SIZE)
        """
        return [head(hidden) for head in self.heads]


class CausalMHA(nn.Module):
    """Multi-head causal self-attention with KV-cache support.

    Parameter names match nn.MultiheadAttention so existing checkpoints
    (trained with nn.TransformerEncoder) load without conversion.
    """

    def __init__(self, d_model: int, nhead: int, dropout: float = 0.0):
        super().__init__()
        assert d_model % nhead == 0
        self.nhead   = nhead
        self.d_head  = d_model // nhead
        self.d_model = d_model
        self.scale   = self.d_head ** -0.5

        # Match nn.MultiheadAttention parameter names exactly
        self.in_proj_weight = nn.Parameter(torch.empty(3 * d_model, d_model))
        self.in_proj_bias   = nn.Parameter(torch.zeros(3 * d_model))
        self.out_proj       = nn.Linear(d_model, d_model, bias=True)
        self.attn_drop      = nn.Dropout(dropout)

        nn.init.xavier_uniform_(self.in_proj_weight)
        nn.init.zeros_(self.out_proj.bias)

    def forward(
        self,
        x: torch.Tensor,           # (B, T, C)
        past_kv: Optional[Tuple[torch.Tensor, torch.Tensor]] = None,
    ) -> Tuple[torch.Tensor, Tuple[torch.Tensor, torch.Tensor]]:
        B, T, C = x.shape
        H, D    = self.nhead, self.d_head

        # Packed QKV projection
        QKV = F.linear(x, self.in_proj_weight, self.in_proj_bias)
        Q, K, V = QKV.split(C, dim=-1)

        Q = Q.view(B, T, H, D).transpose(1, 2)   # (B, H, T,  D)
        K = K.view(B, T, H, D).transpose(1, 2)
        V = V.view(B, T, H, D).transpose(1, 2)

        # Append past cache
        if past_kv is not None:
            K = torch.cat([past_kv[0], K], dim=2)
            V = torch.cat([past_kv[1], V], dim=2)

        new_kv: Tuple[torch.Tensor, torch.Tensor] = (K, V)

        T_q  = Q.shape[2]
        T_kv = K.shape[2]

        attn = (Q @ K.transpose(-2, -1)) * self.scale   # (B, H, T_q, T_kv)

        # Causal mask only needed during prefill (T_q > 1)
        if T_q > 1:
            bias = torch.full((T_q, T_kv), float('-inf'), device=x.device)
            bias = torch.triu(bias, diagonal=T_kv - T_q + 1)
            attn = attn + bias

        attn = self.attn_drop(F.softmax(attn, dim=-1))
        out  = (attn @ V).transpose(1, 2).contiguous().view(B, T_q, C)
        return F.linear(out, self.out_proj.weight, self.out_proj.bias), new_kv


class CausalTransformerLayer(nn.Module):
    """Pre-norm transformer layer with KV-cache.

    Parameter layout matches nn.TransformerEncoderLayer(norm_first=True)
    so existing checkpoint weights load without conversion.
    """

    def __init__(self, d_model: int, nhead: int, dim_feedforward: int, dropout: float = 0.0):
        super().__init__()
        self.self_attn = CausalMHA(d_model, nhead, dropout)
        self.linear1   = nn.Linear(d_model, dim_feedforward)
        self.linear2   = nn.Linear(dim_feedforward, d_model)
        self.norm1     = nn.LayerNorm(d_model)
        self.norm2     = nn.LayerNorm(d_model)
        self.dropout   = nn.Dropout(dropout)   # used in FF block
        self.dropout1  = nn.Dropout(dropout)   # after attn
        self.dropout2  = nn.Dropout(dropout)   # after FF

    def forward(
        self,
        x: torch.Tensor,
        past_kv: Optional[Tuple[torch.Tensor, torch.Tensor]] = None,
    ) -> Tuple[torch.Tensor, Tuple[torch.Tensor, torch.Tensor]]:
        # Pre-norm self-attention
        attn_out, new_kv = self.self_attn(self.norm1(x), past_kv)
        x = x + self.dropout1(attn_out)
        # Pre-norm feed-forward
        x = x + self.dropout2(self.linear2(self.dropout(F.gelu(self.linear1(self.norm2(x))))))
        return x, new_kv


class CausalTransformer(nn.Module):
    """Stack of CausalTransformerLayers with KV-cache pass-through.

    Drop-in replacement for nn.TransformerEncoder — same parameter names,
    same checkpoint compatibility, extended forward signature.
    """

    def __init__(self, layer: CausalTransformerLayer, num_layers: int):
        super().__init__()
        import copy
        self.layers = nn.ModuleList([copy.deepcopy(layer) for _ in range(num_layers)])

    def forward(
        self,
        x: torch.Tensor,
        past_kvs: Optional[List] = None,
        mask=None,       # accepted but unused — causal masking is internal
        is_causal=False, # accepted but unused
    ) -> Tuple[torch.Tensor, List]:
        new_kvs = []
        for i, layer in enumerate(self.layers):
            pkv = past_kvs[i] if past_kvs is not None else None
            x, nkv = layer(x, pkv)
            new_kvs.append(nkv)
        return x, new_kvs


class ApolloModel(nn.Module):
    """Compound-event autoregressive Transformer with spectral awareness.

    Architecture:
        Input:  token_emb + pos_emb + spectral_emb + user_emb
                    ↓
                Transformer decoder (causal)
                    ↓
                ┌───┴───┐
            token_head  timbre_head
                ↓           ↓
            logits      timbral descriptors
    """

    def __init__(
        self,
        vocab_size: int = 380,
        d_model: int = 256,
        nhead: int = 4,
        num_layers: int = 4,
        max_seq_len: int = 1024,
        user_embed_dim: int = 32,
        spectral_dim: int = 21,    # 5 note-level + 16 trajectory
        n_timbre_outputs: int = 5,  # brightness, attack, richness, warmth, flux
        dropout: float = 0.1,
        n_mels: int = 0,           # 0 = mel encoder disabled
    ):
        super().__init__()
        self.d_model = d_model
        self.max_seq_len = max_seq_len
        self.vocab_size = vocab_size

        # Token embedding + positional encoding
        self.token_embedding = nn.Embedding(vocab_size, d_model)
        self.pos_embedding = nn.Embedding(max_seq_len, d_model)
        self.dropout = nn.Dropout(dropout)

        # Spectral feature encoder (continuous side-channel — 5 hand-crafted scalars)
        self.spectral_encoder = SpectralEncoder(spectral_dim, d_model) if spectral_dim > 0 else None
        self.spectral_dim = spectral_dim

        # Mel spectrogram encoder (Phase 3 — learned audio conditioning)
        self.mel_encoder = MelEncoder(n_mels, d_model) if n_mels > 0 else None

        # Optional user embedding projection
        self.user_proj = nn.Linear(user_embed_dim, d_model) if user_embed_dim > 0 else None

        # Causal transformer with KV-cache support
        _layer = CausalTransformerLayer(
            d_model=d_model,
            nhead=nhead,
            dim_feedforward=d_model * 4,
            dropout=dropout,
        )
        self.transformer = CausalTransformer(_layer, num_layers=num_layers)
        self.norm = nn.LayerNorm(d_model)

        # Output heads
        self.token_head = nn.Linear(d_model, vocab_size)
        self.timbre_head = TimbrePredictor(d_model, n_timbre_outputs) if n_timbre_outputs > 0 else None
        self.n_timbre_outputs = n_timbre_outputs

        self._init_weights()

    def _init_weights(self):
        for p in self.parameters():
            if p.dim() > 1:
                nn.init.xavier_uniform_(p)

    def _expand_spectral_to_tokens(
        self,
        spectral_features: torch.Tensor,  # (B, N_events, spectral_dim)
        tokens_per_event: int = 5,
        total_tokens: int = None,
    ) -> torch.Tensor:
        """Expand event-level spectral features to match token-level sequence.

        Each event produces `tokens_per_event` tokens, so we repeat each
        event's spectral embedding for all its tokens.

        Also handles BOS/EOS/SEP special tokens by zero-padding.
        """
        B, N_events, D = spectral_features.shape
        # Repeat each event's features for each of its tokens
        expanded = spectral_features.repeat_interleave(tokens_per_event, dim=1)

        if total_tokens is not None and expanded.shape[1] != total_tokens:
            # Pad or truncate to match actual token sequence length
            if expanded.shape[1] < total_tokens:
                pad = torch.zeros(B, total_tokens - expanded.shape[1], D,
                                  device=spectral_features.device)
                expanded = torch.cat([expanded, pad], dim=1)
            else:
                expanded = expanded[:, :total_tokens, :]

        return expanded

    def forward(
        self,
        tokens: torch.Tensor,                              # (B, T)
        spectral_features: Optional[torch.Tensor] = None,  # (B, N_events, spectral_dim)
        user_embedding: Optional[torch.Tensor] = None,     # (B, user_embed_dim)
        tokens_per_event: int = 5,
        mel_patch: Optional[torch.Tensor] = None,          # (B, mel_frames, n_mels)
        past_kvs: Optional[List] = None,                   # KV cache from previous step
        return_past_kvs: bool = False,                     # whether to include cache in output
        position_offset: int = 0,                          # token position of x[:,0] in full seq
    ) -> Dict[str, torch.Tensor]:
        """Forward pass with optional KV-cache for fast incremental decoding.

        For full-sequence (prefill) pass: call with past_kvs=None.
        For single-token (decode) pass:  call with past_kvs=<previous output['past_kvs']>
                                         and position_offset=<current sequence length - 1>.

        Returns dict with:
            'logits':    (B, T, vocab_size)
            'timbre':    (B, T, n_timbre_outputs)  — if timbre_head present
            'past_kvs':  list[(K,V)] per layer     — if return_past_kvs=True
        """
        B, T = tokens.shape
        device = tokens.device

        # Token + position embeddings
        tok_emb = self.token_embedding(tokens)
        pos = torch.arange(T, device=device).unsqueeze(0) + position_offset
        pos = pos.clamp(max=self.max_seq_len - 1)
        pos_emb = self.pos_embedding(pos)
        h = self.dropout(tok_emb + pos_emb)

        # Mel conditioning
        if mel_patch is not None and self.mel_encoder is not None:
            h = h + self.mel_encoder(mel_patch)

        # Scalar spectral conditioning (legacy)
        if spectral_features is not None and self.spectral_encoder is not None:
            spectral_emb = self.spectral_encoder(spectral_features)
            spectral_expanded = self._expand_spectral_to_tokens(
                spectral_emb, tokens_per_event=tokens_per_event, total_tokens=T
            )
            h = h + spectral_expanded

        # User embedding
        if user_embedding is not None and self.user_proj is not None:
            h = h + self.user_proj(user_embedding).unsqueeze(1)

        # Transformer (KV-cache aware)
        h, new_kvs = self.transformer(h, past_kvs=past_kvs)
        h = self.norm(h)

        result: Dict[str, torch.Tensor] = {'logits': self.token_head(h)}
        if self.timbre_head is not None:
            result['timbre'] = self.timbre_head(h)
        if return_past_kvs:
            result['past_kvs'] = new_kvs

        return result

    @torch.no_grad()
    def generate(
        self,
        prompt: torch.Tensor,
        max_new_tokens: int = 256,
        temperature: float = 0.9,
        top_k: int = 50,
        user_embedding: Optional[torch.Tensor] = None,
        spectral_features: Optional[torch.Tensor] = None,
        tokens_per_event: int = 5,
        mel_patch: Optional[torch.Tensor] = None,
    ) -> Tuple[torch.Tensor, Optional[torch.Tensor]]:
        """Autoregressive generation with KV-cache (O(T) per step after prefill).

        Returns:
            tokens: (1, T_prompt + T_generated)
            timbre_predictions: (1, N_generated, n_timbre_outputs) or None
        """
        self.eval()
        tokens = prompt.clone()
        timbre_preds: List[torch.Tensor] = []

        # ── Prefill ───────────────────────────────────────────────────────────
        # Process the full prompt once to build the initial KV cache.
        output   = self(
            tokens,
            spectral_features=spectral_features,
            user_embedding=user_embedding,
            tokens_per_event=tokens_per_event,
            mel_patch=mel_patch,
            past_kvs=None,
            return_past_kvs=True,
            position_offset=0,
        )
        past_kvs = output['past_kvs']
        offset   = tokens.shape[1]   # position of the next token to generate

        # ── Decode ────────────────────────────────────────────────────────────
        # Feed one token at a time; K/V for all previous positions are cached.
        for _ in range(max_new_tokens):
            last = tokens[:, -1:]   # (B, 1) — only the newest token

            output = self(
                last,
                past_kvs=past_kvs,
                return_past_kvs=True,
                position_offset=offset,
            )
            past_kvs = output['past_kvs']
            offset  += 1

            next_logits = output['logits'][:, -1, :] / temperature
            if top_k > 0:
                v, _ = torch.topk(next_logits, min(top_k, next_logits.size(-1)))
                next_logits[next_logits < v[:, [-1]]] = float('-inf')

            probs      = F.softmax(next_logits, dim=-1)
            next_token = torch.multinomial(probs, num_samples=1)
            tokens     = torch.cat([tokens, next_token], dim=1)

            if self.timbre_head is not None:
                timbre_preds.append(output['timbre'][:, -1, :])

            if next_token.item() == 378:   # EOS
                break

        timbre_out = torch.stack(timbre_preds, dim=1) if timbre_preds else None
        return tokens, timbre_out
