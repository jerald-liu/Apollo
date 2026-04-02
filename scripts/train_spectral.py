"""Apollo spectral-aware training script.

Trains with combined losses:
1. Cross-entropy on next-token prediction (pitch, velocity, timing, duration, pedal)
2. MSE on timbral descriptor prediction (brightness, attack, richness, warmth, flux)

Uses synthesized audio from MIDI for spectral features (full MAESTRO audio preferred).
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / 'Projects' / 'apollo' / 'src'))

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
import numpy as np
import pandas as pd
import pretty_midi
import soundfile as sf
from tqdm import tqdm
import json
import time

from representation import (
    midi_to_events, events_to_tokens, events_to_continuous,
    VOCAB_SIZE, TOKEN_OFFSETS, CONTINUOUS_DIM, TOKENS_PER_EVENT,
)
from spectral import SpectralAnalyzer
from model import ApolloModel

# --- Config ---
DATA_DIR = Path.home() / 'Projects' / 'apollo' / 'data' / 'raw' / 'maestro-v3.0.0'
SYNTH_DIR = DATA_DIR / 'synth_audio'
OUTPUT_DIR = Path.home() / 'Projects' / 'apollo' / 'models'
DOCS_DIR = Path.home() / 'Projects' / 'apollo' / 'docs'

POC_SIZE = 30
MAX_EVENTS = 256
SEQ_LEN = 256
BATCH_SIZE = 16
NUM_EPOCHS = 15
LR = 3e-4
TIMBRE_LOSS_WEIGHT = 0.5  # weight for timbral prediction loss

device = 'cpu'  # MPS had issues; CPU is fine for PoC scale
print(f'Device: {device}')


# --- Dataset ---
class SpectralMusicDataset(Dataset):
    """Dataset of (token_window, spectral_features, timbre_targets) triples."""

    def __init__(self, token_seqs, spectral_seqs, seq_len=256, stride=128):
        """
        Args:
            token_seqs: list of token sequences (List[List[int]])
            spectral_seqs: list of continuous feature arrays (List[np.ndarray])
                Each array is (n_events, CONTINUOUS_DIM)
            seq_len: token window size
            stride: step between windows
        """
        self.windows = []

        for tokens, spectral in zip(token_seqs, spectral_seqs):
            n_events = len(spectral)
            n_tokens = len(tokens)

            for start in range(0, n_tokens - seq_len, stride):
                end = start + seq_len + 1  # +1 for target

                if end > n_tokens:
                    break

                token_window = tokens[start:end]

                # Map token positions back to event indices
                # BOS is at position 0, then every TOKENS_PER_EVENT tokens is one event
                # We need the spectral features for events in this window
                first_event = max(0, (start - 1) // TOKENS_PER_EVENT)
                last_event = min(n_events, (end - 1) // TOKENS_PER_EVENT + 1)
                event_spectral = spectral[first_event:last_event]

                # Timbre targets: the note-level timbral descriptors (first 5 dims)
                # These are what the model should learn to predict
                timbre_targets = event_spectral[:, :5] if len(event_spectral) > 0 else np.zeros((1, 5))

                self.windows.append({
                    'tokens': token_window,
                    'spectral': event_spectral,
                    'timbre_targets': timbre_targets,
                    'n_events': last_event - first_event,
                })

    def __len__(self):
        return len(self.windows)

    def __getitem__(self, idx):
        w = self.windows[idx]
        x = torch.tensor(w['tokens'][:-1], dtype=torch.long)
        y = torch.tensor(w['tokens'][1:], dtype=torch.long)
        spectral = torch.tensor(w['spectral'], dtype=torch.float32)
        timbre = torch.tensor(w['timbre_targets'], dtype=torch.float32)
        return x, y, spectral, timbre


def collate_fn(batch):
    """Custom collation: pad spectral and timbre to max events in batch."""
    xs, ys, specs, timbres = zip(*batch)

    x = torch.stack(xs)
    y = torch.stack(ys)

    max_events = max(s.shape[0] for s in specs)
    spec_dim = specs[0].shape[1] if specs[0].shape[0] > 0 else CONTINUOUS_DIM

    padded_specs = torch.zeros(len(specs), max_events, spec_dim)
    padded_timbres = torch.zeros(len(timbres), max_events, 5)

    for i, (s, t) in enumerate(zip(specs, timbres)):
        n = s.shape[0]
        padded_specs[i, :n] = s
        nt = t.shape[0]
        padded_timbres[i, :nt] = t

    return x, y, padded_specs, padded_timbres


# --- Step 1: Synthesize audio + extract spectral features ---
print('\n=== Step 1: Preparing data with spectral features ===')

meta = pd.read_csv(DATA_DIR / 'maestro-v3.0.0.csv')
train_meta = meta[meta['split'] == 'train'].iloc[:POC_SIZE]
SYNTH_DIR.mkdir(exist_ok=True)

analyzer = SpectralAnalyzer(sr=22050, n_fft=2048, hop_length=512)

# Load normalization stats if available, otherwise compute them
stats_path = DOCS_DIR / 'spectral_normalization_stats.json'
norm_stats = None
if stats_path.exists():
    with open(stats_path) as f:
        norm_stats = json.load(f)
    print(f'Loaded normalization stats from {stats_path}')

all_token_seqs = []
all_spectral_seqs = []
errors = 0

for _, row in tqdm(train_meta.iterrows(), total=len(train_meta), desc='Processing'):
    midi_path = DATA_DIR / row['midi_filename']
    synth_path = SYNTH_DIR / (Path(row['midi_filename']).stem + '.wav')

    try:
        # Synthesize audio if needed
        if not synth_path.exists():
            pm = pretty_midi.PrettyMIDI(str(midi_path))
            audio = pm.synthesize(fs=22050)[:22050 * 60]  # first 60s
            sf.write(str(synth_path), audio, 22050)

        # Extract events with spectral features
        events = midi_to_events(
            str(midi_path),
            max_events=MAX_EVENTS,
            spectral_analyzer=analyzer,
            audio_path=str(synth_path),
            spectral_norm_stats=norm_stats,
        )

        if len(events) < 20:
            continue

        tokens = events_to_tokens(events)
        spectral = events_to_continuous(events)

        all_token_seqs.append(tokens)
        all_spectral_seqs.append(spectral)

    except Exception as e:
        errors += 1
        if errors <= 3:
            print(f'  Error: {e}')

total_tokens = sum(len(s) for s in all_token_seqs)
total_events = sum(len(s) for s in all_spectral_seqs)
print(f'\nProcessed {len(all_token_seqs)} files ({errors} errors)')
print(f'Total tokens: {total_tokens:,}, Total events: {total_events:,}')

# Verify spectral features have variance
if all_spectral_seqs:
    all_spec = np.concatenate(all_spectral_seqs, axis=0)
    print(f'\nSpectral feature stats (across {len(all_spec)} events):')
    for i, name in enumerate(['brightness', 'attack', 'richness', 'warmth', 'flux']):
        vals = all_spec[:, i]
        print(f'  {name:12s}: mean={vals.mean():.3f}, std={vals.std():.3f}, '
              f'range=[{vals.min():.3f}, {vals.max():.3f}]')


# --- Step 2: Create dataset ---
print('\n=== Step 2: Creating dataset ===')

dataset = SpectralMusicDataset(all_token_seqs, all_spectral_seqs, seq_len=SEQ_LEN, stride=128)
val_size = max(1, len(dataset) // 10)
train_size = len(dataset) - val_size
train_ds, val_ds = torch.utils.data.random_split(
    dataset, [train_size, val_size],
    generator=torch.Generator().manual_seed(42)
)
train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True,
                          num_workers=0, collate_fn=collate_fn)
val_loader = DataLoader(val_ds, batch_size=BATCH_SIZE, shuffle=False,
                        num_workers=0, collate_fn=collate_fn)
print(f'Train: {len(train_ds)} windows ({len(train_loader)} batches)')
print(f'Val: {len(val_ds)} windows')


# --- Step 3: Train ---
print('\n=== Step 3: Training spectral-aware model ===')

model = ApolloModel(
    vocab_size=VOCAB_SIZE,
    d_model=256,
    nhead=4,
    num_layers=4,
    max_seq_len=SEQ_LEN,
    user_embed_dim=0,
    spectral_dim=CONTINUOUS_DIM,
    n_timbre_outputs=5,
    dropout=0.1,
).to(device)

n_params = sum(p.numel() for p in model.parameters())
print(f'Model: {n_params:,} params ({n_params/1e6:.2f}M)')

optimizer = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=0.01)
scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=NUM_EPOCHS, eta_min=1e-5)

best_val_loss = float('inf')
history = {'train_total': [], 'train_token': [], 'train_timbre': [],
           'val_total': [], 'val_token': [], 'val_timbre': []}
start_time = time.time()

for epoch in range(NUM_EPOCHS):
    # --- Train ---
    model.train()
    epoch_token_loss = 0
    epoch_timbre_loss = 0
    n_batches = 0

    for x, y, spectral, timbre_targets in train_loader:
        x, y = x.to(device), y.to(device)
        spectral = spectral.to(device)
        timbre_targets = timbre_targets.to(device)

        output = model(x, spectral_features=spectral, tokens_per_event=TOKENS_PER_EVENT)

        # Token prediction loss
        token_loss = F.cross_entropy(output['logits'].view(-1, VOCAB_SIZE), y.view(-1))

        # Timbre prediction loss
        # Align timbre predictions to event positions
        # The timbre head produces predictions at every token position,
        # but targets are at event granularity. Sample at event boundaries.
        timbre_pred = output['timbre']  # (B, T, 5)
        n_target_events = timbre_targets.shape[1]

        # Sample predictions at the last token of each event (pedal token position)
        event_positions = torch.arange(n_target_events, device=device) * TOKENS_PER_EVENT + (TOKENS_PER_EVENT - 1)
        event_positions = event_positions.clamp(max=timbre_pred.shape[1] - 1)
        sampled_pred = timbre_pred[:, event_positions, :]  # (B, n_events, 5)

        # Mask out padding
        mask = (timbre_targets.sum(dim=-1) != 0).float()  # (B, n_events)
        if mask.sum() > 0:
            timbre_loss = ((sampled_pred - timbre_targets) ** 2 * mask.unsqueeze(-1)).sum() / (mask.sum() * 5)
        else:
            timbre_loss = torch.tensor(0.0, device=device)

        # Combined loss
        loss = token_loss + TIMBRE_LOSS_WEIGHT * timbre_loss

        optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()

        epoch_token_loss += token_loss.item()
        epoch_timbre_loss += timbre_loss.item()
        n_batches += 1

    avg_token = epoch_token_loss / n_batches
    avg_timbre = epoch_timbre_loss / n_batches
    history['train_token'].append(avg_token)
    history['train_timbre'].append(avg_timbre)
    history['train_total'].append(avg_token + TIMBRE_LOSS_WEIGHT * avg_timbre)

    # --- Validate ---
    model.eval()
    val_token_loss = 0
    val_timbre_loss = 0
    n_val = 0
    with torch.no_grad():
        for x, y, spectral, timbre_targets in val_loader:
            x, y = x.to(device), y.to(device)
            spectral = spectral.to(device)
            timbre_targets = timbre_targets.to(device)

            output = model(x, spectral_features=spectral, tokens_per_event=TOKENS_PER_EVENT)
            token_loss = F.cross_entropy(output['logits'].view(-1, VOCAB_SIZE), y.view(-1))

            timbre_pred = output['timbre']
            n_target_events = timbre_targets.shape[1]
            event_positions = torch.arange(n_target_events, device=device) * TOKENS_PER_EVENT + (TOKENS_PER_EVENT - 1)
            event_positions = event_positions.clamp(max=timbre_pred.shape[1] - 1)
            sampled_pred = timbre_pred[:, event_positions, :]
            mask = (timbre_targets.sum(dim=-1) != 0).float()
            if mask.sum() > 0:
                timbre_loss = ((sampled_pred - timbre_targets) ** 2 * mask.unsqueeze(-1)).sum() / (mask.sum() * 5)
            else:
                timbre_loss = torch.tensor(0.0, device=device)

            val_token_loss += token_loss.item()
            val_timbre_loss += timbre_loss.item()
            n_val += 1

    avg_val_token = val_token_loss / max(n_val, 1)
    avg_val_timbre = val_timbre_loss / max(n_val, 1)
    avg_val_total = avg_val_token + TIMBRE_LOSS_WEIGHT * avg_val_timbre
    history['val_token'].append(avg_val_token)
    history['val_timbre'].append(avg_val_timbre)
    history['val_total'].append(avg_val_total)

    scheduler.step()

    if avg_val_total < best_val_loss:
        best_val_loss = avg_val_total
        torch.save(model.state_dict(), OUTPUT_DIR / 'apollo_spectral.pt')

    elapsed = time.time() - start_time
    print(f'Epoch {epoch+1:2d}/{NUM_EPOCHS} | '
          f'tok={avg_token:.4f} tmb={avg_timbre:.4f} | '
          f'v_tok={avg_val_token:.4f} v_tmb={avg_val_timbre:.4f} | '
          f'{elapsed:.0f}s')

print(f'\nBest val loss: {best_val_loss:.4f}')
print(f'Training time: {time.time() - start_time:.0f}s')


# --- Step 4: Generate with timbral predictions ---
print('\n=== Step 4: Generating with timbre ===')

model.load_state_dict(torch.load(OUTPUT_DIR / 'apollo_spectral.pt', weights_only=True))
model.eval()

# Use a validation file as prompt
val_meta = meta[meta['split'] == 'validation'].reset_index(drop=True)
prompt_midi = DATA_DIR / val_meta.iloc[0]['midi_filename']
print(f'Prompt: {val_meta.iloc[0]["canonical_title"]} by {val_meta.iloc[0]["canonical_composer"]}')

prompt_events = midi_to_events(str(prompt_midi), max_events=20)
prompt_tokens = events_to_tokens(prompt_events)
prompt_tokens[-1] = TOKEN_OFFSETS['sep']
prompt_spectral = events_to_continuous(prompt_events)

prompt_tensor = torch.tensor([prompt_tokens], dtype=torch.long, device=device)
prompt_spec_tensor = torch.tensor([prompt_spectral], dtype=torch.float32, device=device)

tokens_out, timbre_out = model.generate(
    prompt_tensor,
    max_new_tokens=500,
    temperature=0.9,
    top_k=40,
    spectral_features=prompt_spec_tensor,
    tokens_per_event=TOKENS_PER_EVENT,
)

all_tokens = tokens_out[0].cpu().tolist()
sep_idx = all_tokens.index(TOKEN_OFFSETS['sep']) if TOKEN_OFFSETS['sep'] in all_tokens else len(prompt_tokens) - 1
from representation import tokens_to_events, events_to_midi
gen_events = tokens_to_events([TOKEN_OFFSETS['bos']] + all_tokens[sep_idx + 1:])

print(f'Generated {len(gen_events)} events')

if gen_events and timbre_out is not None:
    # Apply predicted timbral descriptors to generated events
    timbre_np = timbre_out[0].cpu().numpy()
    n_timbre = len(timbre_np)

    for i, e in enumerate(gen_events):
        if i < n_timbre:
            e.brightness = float(timbre_np[i, 0])
            e.attack = float(timbre_np[i, 1])
            e.richness = float(timbre_np[i, 2])
            e.warmth = float(timbre_np[i, 3])
            e.flux = float(timbre_np[i, 4])

    # Print timbre stats
    print('\nPredicted timbral descriptors:')
    for name, idx in [('brightness', 0), ('attack', 1), ('richness', 2), ('warmth', 3), ('flux', 4)]:
        vals = [timbre_np[i, idx] for i in range(min(n_timbre, len(gen_events)))]
        print(f'  {name:12s}: mean={np.mean(vals):.3f}, std={np.std(vals):.3f}, '
              f'range=[{np.min(vals):.3f}, {np.max(vals):.3f}]')

    # Save MIDI with timbral CC messages
    out_path = Path.home() / 'Projects' / 'apollo' / 'data' / 'processed' / 'apollo_spectral.mid'
    combined = prompt_events + gen_events
    pm = events_to_midi(combined, str(out_path))

    # Add timbral CC messages to the MIDI
    inst = pm.instruments[0]
    current_time = sum(e.delta_time for e in prompt_events)
    for e in gen_events:
        current_time += e.delta_time
        # CC 74 = brightness (filter cutoff)
        inst.control_changes.append(
            pretty_midi.ControlChange(74, int(e.brightness * 127), current_time))
        # CC 73 = attack time
        inst.control_changes.append(
            pretty_midi.ControlChange(73, int(e.attack * 127), current_time))
        # CC 71 = richness (resonance)
        inst.control_changes.append(
            pretty_midi.ControlChange(71, int(e.richness * 127), current_time))
    pm.write(str(out_path))

    print(f'\nSaved to {out_path} (with CC 71/73/74 timbral messages)')

# Save training history
history_path = OUTPUT_DIR / 'spectral_training_log.json'
with open(history_path, 'w') as f:
    json.dump(history, f, indent=2)

print('\n=== Spectral Training Complete ===')
print(f'Model saved: {OUTPUT_DIR / "apollo_spectral.pt"}')
print(f'Training log: {history_path}')
print(f'\nThe model now predicts BOTH:')
print(f'  1. Next musical event tokens (pitch, velocity, timing, duration, pedal)')
print(f'  2. Timbral descriptors (brightness, attack, richness, warmth, flux)')
print(f'  → Timbral descriptors are output as MIDI CC for synth control')
