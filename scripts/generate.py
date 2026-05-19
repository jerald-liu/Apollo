"""Apollo Phase 1 — Generation and evaluation script.

Loads a trained checkpoint, generates MIDI from a prompt, and saves
both the generated MIDI and a summary of timbral predictions.

Usage:
    # Generate from a random prompt (BOS token only):
    python scripts/generate.py --checkpoint models/checkpoint_best.pt

    # Generate continuing from an existing MIDI file:
    python scripts/generate.py --checkpoint models/checkpoint_best.pt \
        --prompt data/raw/maestro-v3.0.0/2004/MIDI-Unprocessed_Chamber3_MID--AUDIO_10_R3_2018_wav--1.midi

    # Multiple samples at different temperatures:
    python scripts/generate.py --checkpoint models/checkpoint_best.pt \
        --temperatures 0.7 0.9 1.1 --n-events 128

    # Batch evaluation — generate N samples and report stats:
    python scripts/generate.py --checkpoint models/checkpoint_best.pt \
        --eval --n-samples 16
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
from model import ApolloModel
from representation import (
    midi_to_events, events_to_tokens, tokens_to_events, events_to_midi,
    VOCAB_SIZE, TOKENS_PER_EVENT, TOKEN_OFFSETS,
)


# ---------------------------------------------------------------------------
# Checkpoint loading
# ---------------------------------------------------------------------------

def load_checkpoint(checkpoint_path: str, device: str):
    ckpt = torch.load(checkpoint_path, map_location=device, weights_only=False)
    cfg = ckpt['config']

    model = ApolloModel(
        vocab_size=cfg.get('vocab_size', VOCAB_SIZE),
        d_model=cfg['d_model'],
        nhead=cfg['nhead'],
        num_layers=cfg['num_layers'],
        max_seq_len=cfg['max_seq_len'],
        user_embed_dim=cfg.get('user_embed_dim', 0),
        spectral_dim=cfg['spectral_dim'] if cfg.get('spectral', False) else 0,
        n_timbre_outputs=cfg['n_timbre_outputs'] if cfg.get('spectral', False) else 0,
        dropout=0.0,
        n_mels=cfg.get('n_mels', 0) if cfg.get('mel', False) else 0,
    ).to(device)

    model.load_state_dict(ckpt['model_state_dict'])
    model.eval()

    step = ckpt.get('step', 0)
    val_loss = ckpt.get('best_val_loss', float('inf'))
    print(f'Loaded checkpoint: step={step:,}, best_val_loss={val_loss:.4f}')
    print(f'Model: {sum(p.numel() for p in model.parameters()):,} params  '
          f'd_model={cfg["d_model"]} nhead={cfg["nhead"]} layers={cfg["num_layers"]}')
    return model, cfg, step


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def make_prompt_from_midi(midi_path: str, n_prompt_events: int = 16, device: str = 'cpu'):
    """Build a token prompt from the first N events of a MIDI file."""
    events = midi_to_events(midi_path, max_events=n_prompt_events)
    tokens = events_to_tokens(events[:n_prompt_events])
    t = torch.tensor(tokens, dtype=torch.long, device=device).unsqueeze(0)
    print(f'Prompt: {len(events[:n_prompt_events])} events ({len(tokens)} tokens) from {Path(midi_path).name}')
    return t


def make_bos_prompt(device: str = 'cpu'):
    """Minimal prompt: just the BOS token."""
    t = torch.tensor([[TOKEN_OFFSETS['bos']]], dtype=torch.long, device=device)
    print('Prompt: BOS only (unconditional)')
    return t


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

def generate_sample(
    model: ApolloModel,
    prompt: torch.Tensor,
    n_events: int = 64,
    temperature: float = 0.9,
    top_k: int = 50,
):
    max_new_tokens = n_events * TOKENS_PER_EVENT
    t0 = time.time()

    with torch.no_grad():
        tokens, timbre_preds = model.generate(
            prompt,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            top_k=top_k,
        )

    elapsed = time.time() - t0
    generated = tokens[0, prompt.shape[1]:].tolist()
    events = tokens_to_events(generated)

    ms_per_event = (elapsed / max(len(events), 1)) * 1000
    print(f'Generated {len(events)} events in {elapsed:.2f}s ({ms_per_event:.1f} ms/event)')

    return events, timbre_preds, elapsed


# ---------------------------------------------------------------------------
# Evaluation stats
# ---------------------------------------------------------------------------

def event_stats(events):
    if not events:
        return {}
    pitches = [e.pitch for e in events]
    velocities = [e.velocity for e in events]
    durations = [e.duration for e in events]
    deltas = [e.delta_time for e in events]
    pedal_pct = sum(1 for e in events if e.pedal > 0) / len(events)

    pitch_range = max(pitches) - min(pitches)
    unique_pitches = len(set(pitches))

    return {
        'n_events': len(events),
        'pitch_mean': float(np.mean(pitches)),
        'pitch_range': pitch_range,
        'unique_pitches': unique_pitches,
        'velocity_mean': float(np.mean(velocities)),
        'velocity_std': float(np.std(velocities)),
        'duration_mean': float(np.mean(durations)),
        'ioi_mean': float(np.mean(deltas)),
        'ioi_std': float(np.std(deltas)),
        'pedal_pct': pedal_pct,
    }


def print_stats(stats, prefix=''):
    print(f'{prefix}Events:         {stats["n_events"]}')
    print(f'{prefix}Pitch range:    {stats["pitch_range"]} semitones ({stats["unique_pitches"]} unique)')
    print(f'{prefix}Pitch mean:     {stats["pitch_mean"]:.1f}  (60=middle C)')
    print(f'{prefix}Velocity:       mean={stats["velocity_mean"]:.2f}  std={stats["velocity_std"]:.2f}')
    print(f'{prefix}Duration mean:  {stats["duration_mean"]:.3f}s')
    print(f'{prefix}IOI mean/std:   {stats["ioi_mean"]:.3f}s / {stats["ioi_std"]:.3f}s')
    print(f'{prefix}Pedal usage:    {stats["pedal_pct"]:.0%}')


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='Apollo generation and evaluation')
    parser.add_argument('--checkpoint',   type=str, required=True,   help='Path to .pt checkpoint')
    parser.add_argument('--prompt',       type=str, default=None,     help='MIDI file to use as prompt')
    parser.add_argument('--n-prompt-events', type=int, default=16,    help='Events to take from prompt MIDI')
    parser.add_argument('--n-events',     type=int, default=64,       help='Events to generate per sample')
    parser.add_argument('--temperatures', type=float, nargs='+',      default=[0.9],
                        help='Sampling temperature(s). Multiple → one file per temp.')
    parser.add_argument('--top-k',        type=int, default=50,       help='Top-k sampling')
    parser.add_argument('--output-dir',   type=str, default='data/processed/generated',
                        help='Output directory for MIDI files')
    parser.add_argument('--eval',         action='store_true',        help='Batch eval mode')
    parser.add_argument('--n-samples',    type=int, default=8,        help='Samples for --eval mode')
    parser.add_argument('--device',       type=str, default='auto',   help='auto | cpu | mps | cuda')
    parser.add_argument('--audio',        action='store_true',        help='Render generated MIDI to WAV')
    parser.add_argument('--encodec',      action='store_true',        help='Apply EnCodec neural polish (requires: pip install encodec)')
    parser.add_argument('--sample-rate',  type=int, default=44100,    help='Audio sample rate for --audio output')
    args = parser.parse_args()

    # Device
    if args.device == 'auto':
        if torch.cuda.is_available():
            device = 'cuda'
        elif torch.backends.mps.is_available():
            device = 'mps'
        else:
            device = 'cpu'
    else:
        device = args.device
    print(f'Device: {device}')

    # Load model
    model, cfg, step = load_checkpoint(args.checkpoint, device)

    # Output dir
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    stem = f'step{step}'

    # Prompt
    if args.prompt:
        prompt = make_prompt_from_midi(args.prompt, args.n_prompt_events, device)
    else:
        prompt = make_bos_prompt(device)

    if args.eval:
        # Batch evaluation: generate n_samples at default temp, collect stats
        print(f'\n=== Batch eval: {args.n_samples} samples ===')
        all_stats = []
        for i in range(args.n_samples):
            events, _, _ = generate_sample(model, prompt, args.n_events, args.temperatures[0], args.top_k)
            if events:
                s = event_stats(events)
                all_stats.append(s)
                midi_path = out_dir / f'{stem}_eval_{i:02d}.mid'
                events_to_midi(events, str(midi_path))

        if all_stats:
            print(f'\n--- Aggregate stats ({len(all_stats)} samples) ---')
            for key in all_stats[0]:
                vals = [s[key] for s in all_stats]
                print(f'{key:20s}: mean={np.mean(vals):.3f}  std={np.std(vals):.3f}')

        stats_path = out_dir / f'{stem}_eval_stats.json'
        with open(stats_path, 'w') as f:
            json.dump(all_stats, f, indent=2)
        print(f'\nStats saved to {stats_path}')

    else:
        # Single or multi-temperature generation
        for temp in args.temperatures:
            print(f'\n=== Temperature {temp} ===')
            events, timbre_preds, _ = generate_sample(model, prompt, args.n_events, temp, args.top_k)

            if not events:
                print('No events generated — try a lower temperature or longer prompt')
                continue

            stats = event_stats(events)
            print_stats(stats)

            midi_path = out_dir / f'{stem}_t{str(temp).replace(".", "")}.mid'
            events_to_midi(events, str(midi_path))
            print(f'Saved: {midi_path}')

            if args.audio:
                sys.path.insert(0, str(Path(__file__).parent))
                from synthesize import synthesize_midi
                wav_path = midi_path.with_suffix('.wav')
                synthesize_midi(midi_path, wav_path,
                                sample_rate=args.sample_rate,
                                use_encodec=args.encodec)

            if timbre_preds is not None:
                tp = timbre_preds[0].cpu().numpy()
                print(f'Timbre predictions (mean over events): '
                      f'brightness={tp[:,0].mean():.2f}  attack={tp[:,1].mean():.2f}  '
                      f'richness={tp[:,2].mean():.2f}  warmth={tp[:,3].mean():.2f}  '
                      f'flux={tp[:,4].mean():.2f}')


if __name__ == '__main__':
    main()
