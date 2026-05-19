"""Apollo Phase 1 — Full training script for GPU.

Trains the spectral-aware ApolloModel on preprocessed MAESTRO data.
Supports: multi-GPU (DDP), mixed precision, wandb logging, checkpointing.

Usage:
    # Single GPU:
    python scripts/train.py --config configs/base.yaml

    # Multi-GPU (DDP):
    torchrun --nproc_per_node=4 scripts/train.py --config configs/base.yaml

    # Resume from checkpoint:
    python scripts/train.py --config configs/base.yaml --resume models/checkpoint_latest.pt
"""

import argparse
import json
import math
import os
import random
import sys
import time
from pathlib import Path
from dataclasses import dataclass, asdict

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
from torch.nn.parallel import DistributedDataParallel as DDP
import torch.distributed as dist
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
from model import ApolloModel
from representation import VOCAB_SIZE, CONTINUOUS_DIM, TOKENS_PER_EVENT


# --- Config ---

@dataclass
class TrainConfig:
    # Data
    data_dir: str = 'data/processed'
    spectral: bool = True

    # Model
    vocab_size: int = 380  # override for streaming vocab (259) or custom tokenizers
    d_model: int = 384
    nhead: int = 6
    num_layers: int = 6
    max_seq_len: int = 512
    user_embed_dim: int = 0       # Phase 1: no user embeddings yet
    spectral_dim: int = 21
    n_timbre_outputs: int = 5
    dropout: float = 0.1

    # Training
    batch_size: int = 64
    lr: float = 3e-4
    min_lr: float = 1e-5
    warmup_steps: int = 1000
    max_steps: int = 50000
    weight_decay: float = 0.05
    grad_clip: float = 1.0
    timbre_loss_weight: float = 0.1
    label_smoothing: float = 0.0
    pitch_aug_max: int = 0       # max semitone shift for pitch augmentation (0 = off)
    velocity_aug_range: int = 0  # max bin shift for velocity augmentation (0 = off)

    # Mel spectrogram conditioning (Phase 3)
    mel: bool = False
    n_mels: int = 128
    mel_frames: int = 256

    # torch.compile (PyTorch 2.0+, ~15-30% speedup via Triton kernels)
    use_compile: bool = False

    # Mixed precision
    use_amp: bool = True

    # Logging & checkpointing
    log_interval: int = 50
    eval_interval: int = 500
    save_interval: int = 2000
    output_dir: str = 'models'
    run_name: str = 'apollo_phase1'
    use_wandb: bool = False

    # Validation efficiency
    val_subset_batches: int = 0     # 0 = full val set; >0 = cap each in-training val pass
    early_stop_patience: int = 0    # steps without val improvement before halt; 0 = disabled

    @classmethod
    def from_yaml(cls, path: str) -> 'TrainConfig':
        with open(path) as f:
            data = yaml.safe_load(f)
        # Cast values to declared field types (YAML reads e.g. 3e-4 as string)
        typed = {}
        for k, v in data.items():
            if k in cls.__dataclass_fields__:
                expected_type = cls.__dataclass_fields__[k].type
                if expected_type == float and isinstance(v, str):
                    v = float(v)
                elif expected_type == int and isinstance(v, str):
                    v = int(v)
                typed[k] = v
        return cls(**typed)


# --- Dataset ---

_PITCH_LO, _PITCH_HI = 100, 227   # TOKEN_OFFSETS['pitch'] + 0..127
_VEL_LO,   _VEL_HI   = 228, 259   # TOKEN_OFFSETS['velocity'] + 0..31


def augment_tokens(
    tokens: torch.Tensor,
    pitch_shift: int = 0,
    velocity_shift: int = 0,
) -> torch.Tensor:
    """Apply pitch transposition and velocity jitter in token space."""
    if pitch_shift == 0 and velocity_shift == 0:
        return tokens
    t = tokens.clone()
    if pitch_shift != 0:
        mask = (t >= _PITCH_LO) & (t <= _PITCH_HI)
        t[mask] = (t[mask] + pitch_shift).clamp(_PITCH_LO, _PITCH_HI)
    if velocity_shift != 0:
        mask = (t >= _VEL_LO) & (t <= _VEL_HI)
        t[mask] = (t[mask] + velocity_shift).clamp(_VEL_LO, _VEL_HI)
    return t


class PreprocessedDataset(Dataset):
    """Loads preprocessed .npy token arrays."""

    def __init__(
        self,
        data_dir: str,
        split: str = 'train',
        spectral: bool = True,
        pitch_aug_max: int = 0,
        velocity_aug_range: int = 0,
        mel: bool = False,
    ):
        data_dir = Path(data_dir)
        self.tokens = np.load(data_dir / f'{split}_tokens.npy', mmap_mode='r')
        self.pitch_aug_max = pitch_aug_max
        self.velocity_aug_range = velocity_aug_range
        self.augment = split == 'train' and (pitch_aug_max > 0 or velocity_aug_range > 0)

        cont_path = data_dir / f'{split}_continuous.npy'
        self.continuous = np.load(cont_path, mmap_mode='r') if spectral and cont_path.exists() else None

        mel_path = data_dir / f'{split}_mel.npy'
        self.mel = np.load(mel_path, mmap_mode='r') if mel and mel_path.exists() else None

    def __len__(self):
        return len(self.tokens)

    def __getitem__(self, idx):
        tokens = torch.from_numpy(self.tokens[idx].astype(np.int64))

        if self.augment:
            p_shift = random.randint(-self.pitch_aug_max, self.pitch_aug_max) if self.pitch_aug_max else 0
            v_shift = random.randint(-self.velocity_aug_range, self.velocity_aug_range) if self.velocity_aug_range else 0
            tokens = augment_tokens(tokens, p_shift, v_shift)

        x = tokens[:-1]
        y = tokens[1:]

        cont = torch.from_numpy(self.continuous[idx].astype(np.float32)) if self.continuous is not None else None
        mel  = torch.from_numpy(self.mel[idx].astype(np.float32))        if self.mel  is not None else None

        return x, y, cont, mel


def collate_fn(batch):
    """Custom collate that handles optional continuous features and mel patches."""
    xs, ys, conts, mels = zip(*batch)
    x    = torch.stack(xs)
    y    = torch.stack(ys)
    cont = torch.stack(conts) if conts[0] is not None else None
    mel  = torch.stack(mels)  if mels[0]  is not None else None
    return x, y, cont, mel


# --- Learning rate schedule ---

def get_lr(step: int, config: TrainConfig) -> float:
    """Cosine decay with linear warmup."""
    if step < config.warmup_steps:
        return config.lr * step / config.warmup_steps
    decay_ratio = (step - config.warmup_steps) / max(1, config.max_steps - config.warmup_steps)
    coeff = 0.5 * (1.0 + math.cos(math.pi * decay_ratio))
    return config.min_lr + coeff * (config.lr - config.min_lr)


# --- Training loop ---

def train(config: TrainConfig):
    # Distributed setup
    ddp = int(os.environ.get('RANK', -1)) != -1
    if ddp:
        dist.init_process_group(backend='nccl')
        rank = dist.get_rank()
        local_rank = int(os.environ['LOCAL_RANK'])
        world_size = dist.get_world_size()
        device = f'cuda:{local_rank}'
        torch.cuda.set_device(device)
        master = rank == 0
    else:
        rank = 0
        world_size = 1
        master = True
        if torch.cuda.is_available():
            device = 'cuda'
        elif torch.backends.mps.is_available():
            device = 'mps'
        else:
            device = 'cpu'

    if master:
        print(f'Device: {device}, DDP: {ddp}, World size: {world_size}')
        print(f'Config: {json.dumps(asdict(config), indent=2)}')
        os.makedirs(config.output_dir, exist_ok=True)

    # Wandb
    if config.use_wandb and master:
        try:
            import wandb
            wandb.init(project='apollo', name=config.run_name, config=asdict(config))
        except ImportError:
            print('wandb not installed, skipping')
            config.use_wandb = False

    # Data
    train_dataset = PreprocessedDataset(
        config.data_dir, 'train', config.spectral,
        pitch_aug_max=config.pitch_aug_max,
        velocity_aug_range=config.velocity_aug_range,
        mel=config.mel,
    )
    val_dataset = PreprocessedDataset(
        config.data_dir, 'validation', config.spectral,
        mel=config.mel,
    )

    if ddp:
        train_sampler = torch.utils.data.DistributedSampler(train_dataset, shuffle=True)
        val_sampler = torch.utils.data.DistributedSampler(val_dataset, shuffle=False)
    else:
        train_sampler = None
        val_sampler = None

    pin = device == 'cuda'
    n_workers = 4 if device == 'cuda' else 0

    train_loader = DataLoader(
        train_dataset,
        batch_size=config.batch_size,
        shuffle=(train_sampler is None),
        sampler=train_sampler,
        num_workers=n_workers,
        pin_memory=pin,
        collate_fn=collate_fn,
        drop_last=True,
    )
    val_loader = DataLoader(
        val_dataset,
        batch_size=config.batch_size,
        shuffle=False,
        sampler=val_sampler,
        num_workers=min(n_workers, 2),
        pin_memory=pin,
        collate_fn=collate_fn,
    )

    if master:
        print(f'Train: {len(train_dataset)} windows, {len(train_loader)} batches')
        print(f'Val: {len(val_dataset)} windows, {len(val_loader)} batches')

    # Model
    model = ApolloModel(
        vocab_size=config.vocab_size,
        d_model=config.d_model,
        nhead=config.nhead,
        num_layers=config.num_layers,
        max_seq_len=config.max_seq_len,
        user_embed_dim=config.user_embed_dim,
        spectral_dim=config.spectral_dim if config.spectral else 0,
        n_timbre_outputs=config.n_timbre_outputs if config.spectral else 0,
        dropout=config.dropout,
        n_mels=config.n_mels if config.mel else 0,
    ).to(device)

    n_params = sum(p.numel() for p in model.parameters())
    if master:
        print(f'Model parameters: {n_params:,} ({n_params/1e6:.2f}M)')

    if ddp:
        model = DDP(model, device_ids=[local_rank])
    raw_model = model.module if ddp else model

    # torch.compile — fuses ops into Triton kernels, ~15-30% throughput gain
    if config.use_compile and hasattr(torch, 'compile'):
        model = torch.compile(model)
        if master:
            print('torch.compile enabled')

    # Optimizer
    # Separate weight decay for different parameter groups
    decay_params = [p for n, p in raw_model.named_parameters() if p.dim() >= 2]
    nodecay_params = [p for n, p in raw_model.named_parameters() if p.dim() < 2]
    optim_groups = [
        {'params': decay_params, 'weight_decay': config.weight_decay},
        {'params': nodecay_params, 'weight_decay': 0.0},
    ]
    use_fused = device == 'cuda' and 'fused' in torch.optim.AdamW.__init__.__code__.co_varnames
    optimizer = torch.optim.AdamW(optim_groups, lr=config.lr, betas=(0.9, 0.95), fused=use_fused)

    # AMP scaler
    scaler = torch.amp.GradScaler(enabled=config.use_amp and device == 'cuda')
    amp_dtype = torch.float16 if device == 'cuda' else torch.bfloat16

    # Resume
    start_step = 0
    best_val_loss = float('inf')
    steps_since_best = 0

    # --- Training loop ---
    model.train()
    train_iter = iter(train_loader)
    t0 = time.time()
    running_loss = 0.0
    running_token_loss = 0.0
    running_timbre_loss = 0.0

    for step in range(start_step, config.max_steps):
        # Get batch (cycle through data)
        try:
            x, y, cont, mel = next(train_iter)
        except StopIteration:
            if ddp:
                train_sampler.set_epoch(step)
            train_iter = iter(train_loader)
            x, y, cont, mel = next(train_iter)

        x, y = x.to(device), y.to(device)
        if cont is not None:
            cont = cont.to(device)
        if mel is not None:
            mel = mel.to(device)

        # LR schedule
        lr = get_lr(step, config)
        for pg in optimizer.param_groups:
            pg['lr'] = lr

        # Forward
        with torch.amp.autocast(device_type=device.split(':')[0], dtype=amp_dtype, enabled=config.use_amp):
            output = model(x, spectral_features=cont, tokens_per_event=TOKENS_PER_EVENT, mel_patch=mel)
            logits = output['logits']
            token_loss = F.cross_entropy(
                logits.reshape(-1, config.vocab_size), y.reshape(-1),
                label_smoothing=config.label_smoothing,
            )

            total_loss = token_loss
            timbre_loss = torch.tensor(0.0, device=device)

            if 'timbre' in output and cont is not None:
                # Timbre target: the continuous features shifted by one event
                # We predict the timbral descriptor for the *next* event
                timbre_pred = output['timbre']
                # Extract per-event targets from continuous (first 5 dims = note-level spectral)
                timbre_target = cont[:, :, :5]  # (B, N_events, 5)
                # Expand target to match token-level predictions
                n_events = timbre_target.shape[1]
                target_expanded = timbre_target.repeat_interleave(TOKENS_PER_EVENT, dim=1)
                T_pred = timbre_pred.shape[1]
                T_tgt = target_expanded.shape[1]
                min_T = min(T_pred, T_tgt)
                timbre_loss = F.mse_loss(timbre_pred[:, :min_T], target_expanded[:, :min_T])
                total_loss = token_loss + config.timbre_loss_weight * timbre_loss

        # Backward
        optimizer.zero_grad(set_to_none=True)
        scaler.scale(total_loss).backward()
        scaler.unscale_(optimizer)
        torch.nn.utils.clip_grad_norm_(model.parameters(), config.grad_clip)
        scaler.step(optimizer)
        scaler.update()

        # Logging
        running_loss += total_loss.item()
        running_token_loss += token_loss.item()
        running_timbre_loss += timbre_loss.item()

        if master and (step + 1) % config.log_interval == 0:
            avg_loss = running_loss / config.log_interval
            avg_token = running_token_loss / config.log_interval
            avg_timbre = running_timbre_loss / config.log_interval
            dt = time.time() - t0
            tokens_per_sec = config.batch_size * config.max_seq_len * config.log_interval * world_size / dt

            print(f'step {step+1:>6d} | loss {avg_loss:.4f} | token {avg_token:.4f} | '
                  f'timbre {avg_timbre:.4f} | lr {lr:.2e} | {tokens_per_sec:.0f} tok/s')

            if config.use_wandb:
                import wandb
                wandb.log({
                    'train/loss': avg_loss,
                    'train/token_loss': avg_token,
                    'train/timbre_loss': avg_timbre,
                    'train/lr': lr,
                    'train/tokens_per_sec': tokens_per_sec,
                }, step=step + 1)

            running_loss = 0.0
            running_token_loss = 0.0
            running_timbre_loss = 0.0
            t0 = time.time()

        # Evaluation
        if master and (step + 1) % config.eval_interval == 0:
            model.eval()
            val_loss = 0.0
            val_token_loss = 0.0
            val_timbre_loss = 0.0
            n_val = 0

            with torch.no_grad():
                for vx, vy, vcont, vmel in val_loader:
                    vx, vy = vx.to(device), vy.to(device)
                    if vcont is not None:
                        vcont = vcont.to(device)
                    if vmel is not None:
                        vmel = vmel.to(device)

                    with torch.amp.autocast(device_type=device.split(':')[0], dtype=amp_dtype, enabled=config.use_amp):
                        vout = model(vx, spectral_features=vcont, tokens_per_event=TOKENS_PER_EVENT, mel_patch=vmel)
                        vlogits = vout['logits']
                        vt_loss = F.cross_entropy(vlogits.reshape(-1, config.vocab_size), vy.reshape(-1))

                        vti_loss = torch.tensor(0.0, device=device)
                        if 'timbre' in vout and vcont is not None:
                            timbre_target = vcont[:, :, :5]
                            target_exp = timbre_target.repeat_interleave(TOKENS_PER_EVENT, dim=1)
                            T_p = vout['timbre'].shape[1]
                            T_t = target_exp.shape[1]
                            min_T = min(T_p, T_t)
                            vti_loss = F.mse_loss(vout['timbre'][:, :min_T], target_exp[:, :min_T])

                    val_loss += (vt_loss + config.timbre_loss_weight * vti_loss).item()
                    val_token_loss += vt_loss.item()
                    val_timbre_loss += vti_loss.item()
                    n_val += 1

                    if config.val_subset_batches > 0 and n_val >= config.val_subset_batches:
                        break

            avg_val = val_loss / max(n_val, 1)
            avg_val_tok = val_token_loss / max(n_val, 1)
            avg_val_tim = val_timbre_loss / max(n_val, 1)
            print(f'  VAL step {step+1} | loss {avg_val:.4f} | token {avg_val_tok:.4f} | timbre {avg_val_tim:.4f}')

            if config.use_wandb:
                import wandb
                wandb.log({
                    'val/loss': avg_val,
                    'val/token_loss': avg_val_tok,
                    'val/timbre_loss': avg_val_tim,
                }, step=step + 1)

            if avg_val < best_val_loss:
                best_val_loss = avg_val
                steps_since_best = 0
                save_checkpoint(raw_model, optimizer, step, best_val_loss, config, 'best')
                print(f'  New best model saved (val_loss={avg_val:.4f})')
            else:
                steps_since_best += config.eval_interval

            model.train()

            if config.early_stop_patience > 0 and steps_since_best >= config.early_stop_patience:
                print(
                    f'  Early stop at step {step+1}: no val improvement for '
                    f'{steps_since_best} steps (patience={config.early_stop_patience}, '
                    f'best={best_val_loss:.4f})'
                )
                break

        # Save checkpoint
        if master and (step + 1) % config.save_interval == 0:
            save_checkpoint(raw_model, optimizer, step, best_val_loss, config, 'latest')
            save_checkpoint(raw_model, optimizer, step, best_val_loss, config, f'step_{step+1}')

    # Final save
    if master:
        save_checkpoint(raw_model, optimizer, config.max_steps - 1, best_val_loss, config, 'final')
        print(f'\nTraining complete. Best val loss: {best_val_loss:.4f}')

    if ddp:
        dist.destroy_process_group()


def save_checkpoint(model, optimizer, step, best_val_loss, config, tag):
    path = Path(config.output_dir) / f'checkpoint_{tag}.pt'
    torch.save({
        'model_state_dict': model.state_dict(),
        'optimizer_state_dict': optimizer.state_dict(),
        'step': step,
        'best_val_loss': best_val_loss,
        'config': asdict(config),
    }, path)


def load_checkpoint(path, model, optimizer=None):
    ckpt = torch.load(path, weights_only=False)
    model.load_state_dict(ckpt['model_state_dict'])
    if optimizer and 'optimizer_state_dict' in ckpt:
        optimizer.load_state_dict(ckpt['optimizer_state_dict'])
    return ckpt.get('step', 0), ckpt.get('best_val_loss', float('inf'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=str, default=None, help='Path to YAML config')
    parser.add_argument('--resume', type=str, default=None, help='Resume from checkpoint')
    # Allow CLI overrides for any config field
    for field_name, field_obj in TrainConfig.__dataclass_fields__.items():
        if field_obj.type == bool:
            parser.add_argument(f'--{field_name.replace("_", "-")}', type=lambda x: x.lower() == 'true', default=None)
        elif field_obj.type == int:
            parser.add_argument(f'--{field_name.replace("_", "-")}', type=int, default=None)
        elif field_obj.type == float:
            parser.add_argument(f'--{field_name.replace("_", "-")}', type=float, default=None)
        elif field_obj.type == str:
            parser.add_argument(f'--{field_name.replace("_", "-")}', type=str, default=None)

    args = parser.parse_args()

    if args.config:
        config = TrainConfig.from_yaml(args.config)
    else:
        config = TrainConfig()

    # Apply CLI overrides
    for field_name in TrainConfig.__dataclass_fields__:
        cli_val = getattr(args, field_name, None)
        if cli_val is not None:
            setattr(config, field_name, cli_val)

    train(config)
