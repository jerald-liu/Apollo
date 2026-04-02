"""Preprocess MAESTRO dataset into training-ready format.

Converts all MIDI files (+ optional paired audio) into tokenized sequences
with spectral features, saved as memory-mapped numpy arrays for fast loading.

Usage:
    # MIDI-only (no spectral features):
    python scripts/preprocess.py --midi-dir data/raw/maestro-v3.0.0

    # With paired audio for spectral features:
    python scripts/preprocess.py \
        --midi-dir data/raw/maestro-v3.0.0 \
        --audio-dir data/raw/maestro-v3.0.0 \
        --spectral

    # Quick test run:
    python scripts/preprocess.py --midi-dir data/raw/maestro-v3.0.0 --max-files 10
"""

import argparse
import json
import sys
import time
from pathlib import Path
from multiprocessing import Pool, cpu_count

import numpy as np
import pandas as pd
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from representation import (
    midi_to_events, events_to_tokens, events_to_continuous,
    VOCAB_SIZE, TOKEN_OFFSETS, TOKENS_PER_EVENT, CONTINUOUS_DIM,
)


def process_file(args):
    """Process a single MIDI file. Designed for multiprocessing.Pool."""
    midi_path, audio_path, use_spectral, max_events = args
    try:
        spectral_analyzer = None
        if use_spectral and audio_path and Path(audio_path).exists():
            from spectral import SpectralAnalyzer
            spectral_analyzer = SpectralAnalyzer(sr=22050, n_fft=2048, hop_length=512)

        events = midi_to_events(
            str(midi_path),
            max_events=max_events,
            spectral_analyzer=spectral_analyzer,
            audio_path=str(audio_path) if audio_path else None,
        )

        if len(events) < 10:
            return None

        tokens = events_to_tokens(events)
        continuous = events_to_continuous(events) if use_spectral else None

        return {
            'tokens': tokens,
            'continuous': continuous,
            'n_events': len(events),
            'n_tokens': len(tokens),
        }
    except Exception as e:
        return {'error': str(e), 'file': str(midi_path)}


def create_training_windows(all_tokens, all_continuous, seq_len, stride):
    """Create fixed-length training windows from variable-length sequences.

    Returns:
        token_windows: np.ndarray of shape (N, seq_len+1) — input + target
        continuous_windows: np.ndarray of shape (N, max_events, CONTINUOUS_DIM) or None
    """
    token_windows = []
    continuous_windows = []

    tokens_per_event = TOKENS_PER_EVENT

    for idx, tokens in enumerate(all_tokens):
        for start in range(0, len(tokens) - seq_len, stride):
            window = tokens[start:start + seq_len + 1]
            token_windows.append(window)

            if all_continuous is not None:
                # Map token position back to event index
                # Each event = tokens_per_event tokens, plus BOS at start
                event_start = max(0, (start - 1)) // tokens_per_event
                n_events_in_window = seq_len // tokens_per_event + 1
                cont = all_continuous[idx]
                event_end = min(event_start + n_events_in_window, len(cont))

                cont_window = np.zeros((n_events_in_window, CONTINUOUS_DIM), dtype=np.float32)
                actual = cont[event_start:event_end]
                cont_window[:len(actual)] = actual
                continuous_windows.append(cont_window)

    token_arr = np.array(token_windows, dtype=np.int32)
    cont_arr = np.array(continuous_windows, dtype=np.float32) if continuous_windows else None

    return token_arr, cont_arr


def main():
    parser = argparse.ArgumentParser(description='Preprocess MAESTRO for Apollo training')
    parser.add_argument('--midi-dir', type=str, required=True, help='Path to MAESTRO directory')
    parser.add_argument('--audio-dir', type=str, default=None, help='Path to paired audio (same structure as midi-dir)')
    parser.add_argument('--output-dir', type=str, default='data/processed', help='Output directory')
    parser.add_argument('--spectral', action='store_true', help='Extract spectral features from audio')
    parser.add_argument('--max-events', type=int, default=2048, help='Max events per file')
    parser.add_argument('--max-files', type=int, default=None, help='Limit number of files (for testing)')
    parser.add_argument('--seq-len', type=int, default=512, help='Training sequence length in tokens')
    parser.add_argument('--stride', type=int, default=256, help='Stride between training windows')
    parser.add_argument('--workers', type=int, default=None, help='Number of worker processes')
    args = parser.parse_args()

    midi_dir = Path(args.midi_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load metadata
    csv_path = midi_dir / 'maestro-v3.0.0.csv'
    if not csv_path.exists():
        # Fall back to glob for MIDI files
        midi_files = sorted(midi_dir.rglob('*.mid')) + sorted(midi_dir.rglob('*.midi'))
        meta = pd.DataFrame({'midi_filename': [str(f.relative_to(midi_dir)) for f in midi_files]})
        meta['split'] = 'train'
    else:
        meta = pd.read_csv(csv_path)

    if args.max_files:
        meta = meta.head(args.max_files)

    print(f'Dataset: {len(meta)} files')
    print(f'Spectral features: {"ON" if args.spectral else "OFF"}')
    print(f'Sequence length: {args.seq_len}, stride: {args.stride}')

    # Build file list
    file_args = []
    for _, row in meta.iterrows():
        midi_path = midi_dir / row['midi_filename']
        audio_path = None
        if args.spectral and args.audio_dir:
            # MAESTRO audio files have same name but .wav extension
            audio_name = row.get('audio_filename', row['midi_filename'].replace('.midi', '.wav').replace('.mid', '.wav'))
            audio_path = Path(args.audio_dir) / audio_name
        file_args.append((str(midi_path), str(audio_path) if audio_path else None, args.spectral, args.max_events))

    # Process files
    n_workers = args.workers or max(1, cpu_count() - 1)
    # Use single process if spectral (librosa isn't great with multiprocessing)
    if args.spectral:
        n_workers = 1

    print(f'Processing with {n_workers} workers...')
    start_time = time.time()

    results = []
    if n_workers == 1:
        for fa in tqdm(file_args, desc='Processing'):
            results.append(process_file(fa))
    else:
        with Pool(n_workers) as pool:
            results = list(tqdm(
                pool.imap(process_file, file_args),
                total=len(file_args),
                desc='Processing',
            ))

    elapsed = time.time() - start_time
    print(f'Processing took {elapsed:.1f}s')

    # Separate by split
    errors = [r for r in results if r is not None and 'error' in r]
    valid = [r for r in results if r is not None and 'error' not in r]
    print(f'Valid: {len(valid)}, Errors: {len(errors)}')
    if errors[:3]:
        for e in errors[:3]:
            print(f'  Error: {e["error"][:100]}')

    # Split data
    splits = {'train': [], 'validation': [], 'test': []}
    for i, (_, row) in enumerate(meta.iterrows()):
        if i >= len(results) or results[i] is None or 'error' in results[i]:
            continue
        split = row.get('split', 'train')
        splits[split].append(results[i])

    # Process each split
    for split_name, split_data in splits.items():
        if not split_data:
            print(f'Skip {split_name}: no data')
            continue

        all_tokens = [d['tokens'] for d in split_data]
        all_continuous = [d['continuous'] for d in split_data] if args.spectral else None

        # Filter out None continuous arrays if not all files had audio
        if all_continuous and any(c is None for c in all_continuous):
            paired = [(t, c) for t, c in zip(all_tokens, all_continuous) if c is not None]
            if paired:
                all_tokens, all_continuous = zip(*paired)
                all_tokens, all_continuous = list(all_tokens), list(all_continuous)
            else:
                all_continuous = None

        print(f'\n{split_name}: {len(all_tokens)} files, {sum(len(t) for t in all_tokens):,} total tokens')

        token_arr, cont_arr = create_training_windows(
            all_tokens, all_continuous, args.seq_len, args.stride
        )

        print(f'  Windows: {len(token_arr)} × seq_len={args.seq_len}')

        # Save as numpy files
        np.save(output_dir / f'{split_name}_tokens.npy', token_arr)
        if cont_arr is not None:
            np.save(output_dir / f'{split_name}_continuous.npy', cont_arr)
            print(f'  Continuous shape: {cont_arr.shape}')

    # Save metadata
    meta_out = {
        'vocab_size': VOCAB_SIZE,
        'seq_len': args.seq_len,
        'stride': args.stride,
        'spectral': args.spectral,
        'continuous_dim': CONTINUOUS_DIM if args.spectral else 0,
        'tokens_per_event': TOKENS_PER_EVENT,
        'n_files': len(valid),
        'n_errors': len(errors),
        'splits': {k: len(v) for k, v in splits.items()},
        'processing_time_s': elapsed,
    }
    with open(output_dir / 'meta.json', 'w') as f:
        json.dump(meta_out, f, indent=2)

    print(f'\nSaved to {output_dir}/')
    print(json.dumps(meta_out, indent=2))


if __name__ == '__main__':
    main()
