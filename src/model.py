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
from typing import Optional, Dict, Tuple


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
    ):
        super().__init__()
        self.d_model = d_model
        self.max_seq_len = max_seq_len
        self.vocab_size = vocab_size

        # Token embedding + positional encoding
        self.token_embedding = nn.Embedding(vocab_size, d_model)
        self.pos_embedding = nn.Embedding(max_seq_len, d_model)
        self.dropout = nn.Dropout(dropout)

        # Spectral feature encoder (continuous side-channel)
        self.spectral_encoder = SpectralEncoder(spectral_dim, d_model) if spectral_dim > 0 else None
        self.spectral_dim = spectral_dim

        # Optional user embedding projection
        self.user_proj = nn.Linear(user_embed_dim, d_model) if user_embed_dim > 0 else None

        # Transformer decoder layers
        decoder_layer = nn.TransformerDecoderLayer(
            d_model=d_model,
            nhead=nhead,
            dim_feedforward=d_model * 4,
            dropout=dropout,
            batch_first=True,
            norm_first=True,
        )
        self.transformer = nn.TransformerDecoder(decoder_layer, num_layers=num_layers)
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
    ) -> Dict[str, torch.Tensor]:
        """Forward pass.

        Returns dict with:
            'logits': (B, T, vocab_size) — next-token prediction
            'timbre': (B, T, n_timbre_outputs) — timbral descriptor prediction
        """
        B, T = tokens.shape
        device = tokens.device

        # Token + position embeddings
        tok_emb = self.token_embedding(tokens)
        pos = torch.arange(T, device=device).unsqueeze(0)
        pos_emb = self.pos_embedding(pos)
        h = self.dropout(tok_emb + pos_emb)

        # Add spectral conditioning if provided
        if spectral_features is not None and self.spectral_encoder is not None:
            spectral_emb = self.spectral_encoder(spectral_features)  # (B, N_events, d_model)
            spectral_expanded = self._expand_spectral_to_tokens(
                spectral_emb, tokens_per_event=tokens_per_event, total_tokens=T
            )
            h = h + spectral_expanded

        # Add user embedding as a bias if provided
        if user_embedding is not None and self.user_proj is not None:
            user_bias = self.user_proj(user_embedding).unsqueeze(1)
            h = h + user_bias

        # Causal mask + transform
        causal_mask = nn.Transformer.generate_square_subsequent_mask(T, device=device)
        memory = torch.zeros(B, 1, self.d_model, device=device)
        h = self.transformer(h, memory, tgt_mask=causal_mask)
        h = self.norm(h)

        # Output
        result = {
            'logits': self.token_head(h),
        }
        if self.timbre_head is not None:
            result['timbre'] = self.timbre_head(h)

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
    ) -> Tuple[torch.Tensor, Optional[torch.Tensor]]:
        """Autoregressive generation with top-k sampling.

        Returns:
            tokens: (1, T) generated token sequence
            timbre_predictions: (1, N_new_events, n_timbre_outputs) or None
        """
        self.eval()
        tokens = prompt.clone()
        timbre_preds = []

        for _ in range(max_new_tokens):
            context = tokens[:, -self.max_seq_len:]

            output = self(context, spectral_features, user_embedding, tokens_per_event)
            next_logits = output['logits'][:, -1, :] / temperature

            # Top-k filtering
            if top_k > 0:
                v, _ = torch.topk(next_logits, top_k)
                next_logits[next_logits < v[:, [-1]]] = float('-inf')

            probs = F.softmax(next_logits, dim=-1)
            next_token = torch.multinomial(probs, num_samples=1)
            tokens = torch.cat([tokens, next_token], dim=1)

            # Collect timbre prediction at this step
            if self.timbre_head is not None:
                timbre_preds.append(output['timbre'][:, -1, :])

            # Stop at EOS
            if next_token.item() == 378:
                break

        timbre_out = torch.stack(timbre_preds, dim=1) if timbre_preds else None
        return tokens, timbre_out
