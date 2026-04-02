"""Apollo PoC training script — run directly for speed."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / 'Projects' / 'apollo' / 'src'))

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
import numpy as np
import pandas as pd
from tqdm import tqdm
import json
import time

from representation import (
    midi_to_events, events_to_tokens, tokens_to_events, events_to_midi,
    VOCAB_SIZE, TOKEN_OFFSETS
)
from model import ApolloModel

# --- Config ---
DATA_DIR = Path.home() / 'Projects' / 'apollo' / 'data' / 'raw' / 'maestro-v3.0.0'
OUTPUT_DIR = Path.home() / 'Projects' / 'apollo' / 'models'
MIDI_OUT_DIR = Path.home() / 'Projects' / 'apollo' / 'data' / 'processed'

POC_SIZE = 50        # fewer files for speed
SEQ_LEN = 256
BATCH_SIZE = 32
NUM_EPOCHS = 15
LR = 3e-4

device = 'mps' if torch.backends.mps.is_available() else 'cpu'
print(f'Device: {device}')


# --- Dataset ---
class MusicTokenDataset(Dataset):
    def __init__(self, token_sequences, seq_len=256, stride=128):
        self.windows = []
        for seq in token_sequences:
            for start in range(0, len(seq) - seq_len, stride):
                self.windows.append(seq[start:start + seq_len + 1])

    def __len__(self):
        return len(self.windows)

    def __getitem__(self, idx):
        window = self.windows[idx]
        x = torch.tensor(window[:-1], dtype=torch.long)
        y = torch.tensor(window[1:], dtype=torch.long)
        return x, y


# --- Step 1: Tokenize ---
print('\n=== Step 1: Tokenizing MIDI files ===')
meta = pd.read_csv(DATA_DIR / 'maestro-v3.0.0.csv')
train_meta = meta[meta['split'] == 'train'].iloc[:POC_SIZE]

all_token_seqs = []
for _, row in tqdm(train_meta.iterrows(), total=len(train_meta), desc='Tokenizing'):
    midi_path = DATA_DIR / row['midi_filename']
    try:
        events = midi_to_events(str(midi_path), max_events=512)
        if len(events) < 20:
            continue
        tokens = events_to_tokens(events)
        all_token_seqs.append(tokens)
    except Exception:
        pass

total_tokens = sum(len(s) for s in all_token_seqs)
print(f'Processed {len(all_token_seqs)} files, {total_tokens:,} tokens')

dataset = MusicTokenDataset(all_token_seqs, seq_len=SEQ_LEN, stride=128)
val_size = max(1, len(dataset) // 10)
train_size = len(dataset) - val_size
train_ds, val_ds = torch.utils.data.random_split(
    dataset, [train_size, val_size],
    generator=torch.Generator().manual_seed(42)
)
train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True, num_workers=0)
val_loader = DataLoader(val_ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=0)
print(f'Train: {len(train_ds)} windows ({len(train_loader)} batches), Val: {len(val_ds)} windows')


# --- Step 2: Train ---
print('\n=== Step 2: Training ===')
model = ApolloModel(
    vocab_size=VOCAB_SIZE, d_model=256, nhead=4, num_layers=4,
    max_seq_len=SEQ_LEN, user_embed_dim=0, dropout=0.1,
).to(device)

n_params = sum(p.numel() for p in model.parameters())
print(f'Model: {n_params:,} params ({n_params/1e6:.2f}M)')

optimizer = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=0.01)
scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=NUM_EPOCHS, eta_min=1e-5)

best_val_loss = float('inf')
train_losses = []
val_losses = []
start_time = time.time()

for epoch in range(NUM_EPOCHS):
    model.train()
    epoch_loss = 0
    n_batches = 0
    for x, y in train_loader:
        x, y = x.to(device), y.to(device)
        logits = model(x)
        loss = F.cross_entropy(logits.view(-1, VOCAB_SIZE), y.view(-1))
        optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        epoch_loss += loss.item()
        n_batches += 1

    avg_train = epoch_loss / n_batches
    train_losses.append(avg_train)

    model.eval()
    val_loss = 0
    n_val = 0
    with torch.no_grad():
        for x, y in val_loader:
            x, y = x.to(device), y.to(device)
            logits = model(x)
            loss = F.cross_entropy(logits.view(-1, VOCAB_SIZE), y.view(-1))
            val_loss += loss.item()
            n_val += 1

    avg_val = val_loss / max(n_val, 1)
    val_losses.append(avg_val)
    scheduler.step()

    if avg_val < best_val_loss:
        best_val_loss = avg_val
        torch.save(model.state_dict(), OUTPUT_DIR / 'apollo_poc.pt')

    elapsed = time.time() - start_time
    print(f'Epoch {epoch+1:2d}/{NUM_EPOCHS} | train={avg_train:.4f} val={avg_val:.4f} | lr={scheduler.get_last_lr()[0]:.6f} | {elapsed:.0f}s')

print(f'\nBest val loss: {best_val_loss:.4f}')
print(f'Total training time: {time.time() - start_time:.0f}s')


# --- Step 3: Generate ---
print('\n=== Step 3: Generating ===')
model.load_state_dict(torch.load(OUTPUT_DIR / 'apollo_poc.pt', weights_only=True))
model.eval()

val_meta = meta[meta['split'] == 'validation'].reset_index(drop=True)
prompt_path = DATA_DIR / val_meta.iloc[0]['midi_filename']
print(f'Prompt: {val_meta.iloc[0]["canonical_title"]} by {val_meta.iloc[0]["canonical_composer"]}')

prompt_events = midi_to_events(str(prompt_path), max_events=20)
prompt_tokens = events_to_tokens(prompt_events)
prompt_tokens[-1] = TOKEN_OFFSETS['sep']

for temp in [0.7, 0.9, 1.1]:
    prompt_tensor = torch.tensor([prompt_tokens], dtype=torch.long, device=device)
    output_tokens = model.generate(prompt_tensor, max_new_tokens=500, temperature=temp, top_k=40)

    all_tokens = output_tokens[0].cpu().tolist()
    sep_idx = all_tokens.index(TOKEN_OFFSETS['sep']) if TOKEN_OFFSETS['sep'] in all_tokens else len(prompt_tokens) - 1
    gen_tokens = all_tokens[sep_idx + 1:]
    gen_events = tokens_to_events([TOKEN_OFFSETS['bos']] + gen_tokens)

    print(f'\nTemp={temp}: {len(gen_events)} events')
    if gen_events:
        combined = prompt_events + gen_events
        out_path = MIDI_OUT_DIR / f'apollo_poc_temp{temp}.mid'
        events_to_midi(combined, str(out_path))
        print(f'  Saved: {out_path}')
        pitches = [e.pitch for e in gen_events]
        vels = [e.velocity for e in gen_events]
        print(f'  Pitch: {min(pitches)}-{max(pitches)}, Vel: {min(vels):.2f}-{max(vels):.2f}')
        print(f'  First 10 pitches: {pitches[:10]}')

# Save training log
log = {
    'train_losses': train_losses,
    'val_losses': val_losses,
    'best_val_loss': best_val_loss,
    'n_params': n_params,
    'poc_size': POC_SIZE,
    'seq_len': SEQ_LEN,
    'epochs': NUM_EPOCHS,
}
with open(OUTPUT_DIR / 'poc_training_log.json', 'w') as f:
    json.dump(log, f, indent=2)

print('\n=== PoC Complete ===')
