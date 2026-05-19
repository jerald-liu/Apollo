"""Preprocess MAESTRO dataset into training-ready format.

Converts all MIDI files (+ optional paired audio) into tokenized sequences
with spectral features and/or mel spectrograms, saved as memory-mapped
numpy arrays for fast loading.

Usage:
    # MIDI-only (no spectral features):
    python scripts/preprocess.py --midi-dir data/raw/maestro-v3.0.0

    # With paired audio for 5-scalar spectral features:
    python scripts/preprocess.py \\
        --midi-dir data/raw/maestro-v3.0.0 \\
        --audio-dir data/raw/maestro-v3.0.0 \\
        --spectral

    # With mel spectrograms (Phase 3):
    python scripts/preprocess.py \\
        --midi-dir data/raw/maestro-v3.0.0 \\
        --audio-dir data/raw/maestro-v3.0.0 \\
        --mel

    # Quick test run:
    python scripts/preprocess.py --midi-dir data/raw/maestro-v3.0.0 --max-files 10
"""

import argparse
import json
import sys
import time
from collections import defaultdict
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

# Mel defaults — match SpectralAnalyzer conventions
MEL_SR         = 22050
MEL_N_FFT      = 2048
MEL_HOP_LENGTH = 512   # ~23ms per frame
MEL_N_MELS     = 128


def process_file(args):
    """Process a single MIDI file. Designed for multiprocessing.Pool."""
    midi_path, audio_path, use_spectral, max_events = args
    try:
        spectral_analyzer = None
        if use_spectral and audio_path and Path(audio_path).exists():
            from spectral import SpectralAnalyzer
            spectral_analyzer = SpectralAnalyzer(
                sr=MEL_SR, n_fft=MEL_N_FFT, hop_length=MEL_HOP_LENGTH
            )

        events = midi_to_events(
            str(midi_path),
            max_events=max_events,
            spectral_analyzer=spectral_analyzer,
            audio_path=str(audio_path) if audio_path else None,
        )

        if len(events) < 10:
            return None

        tokens     = events_to_tokens(events)
        continuous = events_to_continuous(events) if use_spectral else None
        # Absolute onset time (seconds) for each event — used for mel alignment
        onset_times = np.array([e.onset_time for e in events], dtype=np.float32)

        return {
            'tokens':      tokens,
            'continuous':  continuous,
            'onset_times': onset_times,
            'n_events':    len(events),
            'n_tokens':    len(tokens),
        }
    except Exception as e:
        return {'error': str(e), 'file': str(midi_path)}


def create_training_windows(all_tokens, all_continuous, seq_len, stride, *, all_onset_times=None):
    """Create fixed-length training windows from variable-length sequences.

    Returns:
        token_arr:        (N, seq_len+1) int32 — input + target tokens
        cont_arr:         (N, max_events, CONTINUOUS_DIM) float32 or None
        window_times_arr: (N,) float32 — onset time (s) of first event per window
        file_idx_arr:     (N,) int32  — which source file each window came from
    """
    token_windows      = []
    continuous_windows = []
    window_times       = []
    file_indices       = []

    for file_idx, tokens in enumerate(all_tokens):
        onset_times = all_onset_times[file_idx] if all_onset_times is not None else None

        for start in range(0, len(tokens) - seq_len, stride):
            window = tokens[start:start + seq_len + 1]
            token_windows.append(window)
            file_indices.append(file_idx)

            # Map token position → event index
            event_idx = max(0, (start - 1)) // TOKENS_PER_EVENT
            if onset_times is not None and event_idx < len(onset_times):
                window_times.append(float(onset_times[event_idx]))
            else:
                window_times.append(0.0)

            if all_continuous is not None:
                cont       = all_continuous[file_idx]
                n_evt_win  = seq_len // TOKENS_PER_EVENT + 1
                event_end  = min(event_idx + n_evt_win, len(cont))
                cont_win   = np.zeros((n_evt_win, CONTINUOUS_DIM), dtype=np.float32)
                actual     = cont[event_idx:event_end]
                cont_win[:len(actual)] = actual
                continuous_windows.append(cont_win)

    token_arr        = np.array(token_windows, dtype=np.int32)
    window_times_arr = np.array(window_times,  dtype=np.float32)
    file_idx_arr     = np.array(file_indices,  dtype=np.int32)
    cont_arr         = np.array(continuous_windows, dtype=np.float32) if continuous_windows else None

    return token_arr, cont_arr, window_times_arr, file_idx_arr


def extract_mel_windows(
    audio_paths,       # list[str | None], indexed by file_idx
    file_idx_arr,      # (N,) int32 — which file each window came from
    window_times_arr,  # (N,) float32 — onset time (s) of each window
    mel_frames,        # int — fixed number of frames per patch
    n_mels=MEL_N_MELS,
):
    """Extract a log-mel patch for every training window.

    Returns np.ndarray of shape (N, mel_frames, n_mels) float16.
    Windows whose audio file is missing are filled with zeros.
    """
    import librosa  # imported here so MIDI-only runs don't need it

    n_windows = len(file_idx_arr)
    mel_patches = np.zeros((n_windows, mel_frames, n_mels), dtype=np.float16)

    # Group windows by file so each audio file is loaded only once
    file_to_wins = defaultdict(list)
    for win_idx, fid in enumerate(file_idx_arr):
        file_to_wins[int(fid)].append(win_idx)

    for fid, win_indices in tqdm(file_to_wins.items(), desc='  Mel extraction', leave=False):
        apath = audio_paths[fid]
        if apath is None or not Path(apath).exists():
            # zeros already set
            continue

        try:
            y, _ = librosa.load(apath, sr=MEL_SR, mono=True)
            S    = librosa.feature.melspectrogram(
                y=y, sr=MEL_SR,
                n_fft=MEL_N_FFT, hop_length=MEL_HOP_LENGTH,
                n_mels=n_mels, fmax=8000,
            )
            log_mel = librosa.power_to_db(S, ref=np.max).T  # (n_total_frames, n_mels)

            # Normalize to [0, 1] per file
            lo, hi = log_mel.min(), log_mel.max()
            if hi - lo > 1e-6:
                log_mel = (log_mel - lo) / (hi - lo)
            else:
                log_mel = np.full_like(log_mel, 0.5)

            for win_idx in win_indices:
                t_start     = float(window_times_arr[win_idx])
                frame_start = int(t_start * MEL_SR / MEL_HOP_LENGTH)
                frame_end   = frame_start + mel_frames
                n_avail     = len(log_mel)

                patch = np.zeros((mel_frames, n_mels), dtype=np.float32)
                if frame_start < n_avail:
                    actual_end = min(frame_end, n_avail)
                    chunk      = log_mel[frame_start:actual_end]
                    patch[:len(chunk)] = chunk

                mel_patches[win_idx] = patch.astype(np.float16)

        except Exception as e:
            print(f'  Warning: mel failed for {apath}: {e}')

    return mel_patches


def _preprocess_streaming(args):
    """Preprocess MAESTRO using the streaming note-on/note-off tokenizer.

    Outputs go to a separate directory (default: data/processed_streaming) so
    that base and streaming datasets can coexist on the same machine/volume.
    """
    sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
    from streaming_representation import (
        midi_to_streaming_tokens, VOCAB_SIZE as S_VOCAB_SIZE,
        OFFSETS as S_OFFSETS, TOKENS_PER_NOTE_ON, TOKENS_PER_NOTE_OFF,
    )

    midi_dir   = Path(args.midi_dir)
    output_dir = Path(args.output_dir.replace('processed', 'processed_streaming'))
    output_dir.mkdir(parents=True, exist_ok=True)
    seq_len    = args.seq_len
    stride     = args.stride

    csv_path = midi_dir / 'maestro-v3.0.0.csv'
    if not csv_path.exists():
        midi_files = sorted(midi_dir.rglob('*.mid')) + sorted(midi_dir.rglob('*.midi'))
        meta = pd.DataFrame({'midi_filename': [str(f.relative_to(midi_dir)) for f in midi_files]})
        meta['split'] = 'train'
    else:
        meta = pd.read_csv(csv_path)

    if args.max_files:
        meta = meta.head(args.max_files)

    print(f'Streaming preprocess: {len(meta)} files → {output_dir}')
    print(f'Vocab size: {S_VOCAB_SIZE} | seq_len: {seq_len} | stride: {stride}')

    splits = {'train': [], 'validation': [], 'test': []}
    errors = 0

    for _, row in tqdm(meta.iterrows(), total=len(meta), desc='Tokenising'):
        midi_path = midi_dir / row['midi_filename']
        split     = row.get('split', 'train')
        try:
            tokens = midi_to_streaming_tokens(str(midi_path), max_events=args.max_events)
            if len(tokens) >= seq_len + 1:
                splits[split].append(tokens)
        except Exception as e:
            errors += 1

    print(f'Done. Errors: {errors}')

    for split_name, all_tokens in splits.items():
        if not all_tokens:
            continue
        windows = []
        for tokens in all_tokens:
            for start in range(0, len(tokens) - seq_len, stride):
                windows.append(tokens[start:start + seq_len + 1])
        arr = np.array(windows, dtype=np.int32)
        np.save(output_dir / f'{split_name}_tokens.npy', arr)
        print(f'  {split_name}: {len(arr)} windows  shape={arr.shape}')

    meta_out = {
        'vocab_size':       S_VOCAB_SIZE,
        'seq_len':          seq_len,
        'stride':           stride,
        'streaming':        True,
        'spectral':         False,
        'mel':              False,
        'continuous_dim':   0,
        'tokens_per_note_on':  TOKENS_PER_NOTE_ON,
        'tokens_per_note_off': TOKENS_PER_NOTE_OFF,
        'n_files':          sum(len(v) for v in splits.values()),
        'n_errors':         errors,
        'splits':           {k: len(v) for k, v in splits.items()},
    }
    with open(output_dir / 'meta.json', 'w') as f:
        json.dump(meta_out, f, indent=2)
    print(f'meta.json written to {output_dir}/')
    print(json.dumps(meta_out, indent=2))


def main():
    parser = argparse.ArgumentParser(description='Preprocess MAESTRO for Apollo training')
    parser.add_argument('--midi-dir',   type=str, required=True, help='Path to MAESTRO directory')
    parser.add_argument('--audio-dir',  type=str, default=None,  help='Path to paired audio (same structure as midi-dir)')
    parser.add_argument('--output-dir', type=str, default='data/processed', help='Output directory')
    parser.add_argument('--spectral',   action='store_true', help='Extract 5-scalar spectral features from audio')
    parser.add_argument('--mel',        action='store_true', help='Extract log-mel spectrogram patches from audio (Phase 3)')
    parser.add_argument('--streaming',  action='store_true', help='Use note-on/note-off streaming tokenizer (259-token vocab, Phase 4)')
    parser.add_argument('--mel-frames', type=int, default=256,       help='Mel frames per training window (~5.9s at hop=512)')
    parser.add_argument('--n-mels',     type=int, default=MEL_N_MELS, help='Number of mel bins')
    parser.add_argument('--max-events', type=int, default=2048, help='Max events per file')
    parser.add_argument('--max-files',  type=int, default=None, help='Limit number of files (for testing)')
    parser.add_argument('--seq-len',    type=int, default=512,  help='Training sequence length in tokens')
    parser.add_argument('--stride',     type=int, default=256,  help='Stride between training windows')
    parser.add_argument('--workers',    type=int, default=None, help='Number of worker processes')
    args = parser.parse_args()

    need_audio = args.spectral or args.mel
    audio_base = Path(args.audio_dir) if args.audio_dir else Path(args.midi_dir)

    # Streaming mode: separate output dir + different tokenizer
    if args.streaming:
        _preprocess_streaming(args)
        return

    midi_dir   = Path(args.midi_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load metadata
    csv_path = midi_dir / 'maestro-v3.0.0.csv'
    if not csv_path.exists():
        midi_files = sorted(midi_dir.rglob('*.mid')) + sorted(midi_dir.rglob('*.midi'))
        meta = pd.DataFrame({'midi_filename': [str(f.relative_to(midi_dir)) for f in midi_files]})
        meta['split'] = 'train'
    else:
        meta = pd.read_csv(csv_path)

    if args.max_files:
        meta = meta.head(args.max_files)

    print(f'Dataset:          {len(meta)} files')
    print(f'Spectral scalars: {"ON" if args.spectral else "off"}')
    print(f'Mel spectrograms: {"ON" if args.mel else "off"}')
    if args.mel:
        print(f'  mel_frames={args.mel_frames}, n_mels={args.n_mels}')
    print(f'Sequence length:  {args.seq_len}, stride: {args.stride}')

    # Build file list — track audio path per file for mel extraction
    file_args   = []
    audio_paths = []   # parallel to meta rows

    for _, row in meta.iterrows():
        midi_path  = midi_dir / row['midi_filename']
        audio_path = None
        if need_audio:
            audio_name = row.get(
                'audio_filename',
                row['midi_filename'].replace('.midi', '.wav').replace('.mid', '.wav'),
            )
            audio_path = audio_base / audio_name
        file_args.append((
            str(midi_path),
            str(audio_path) if audio_path else None,
            args.spectral,
            args.max_events,
        ))
        audio_paths.append(str(audio_path) if audio_path else None)

    # Process files (tokenize + optional 5-scalar spectral)
    n_workers = args.workers or max(1, cpu_count() - 1)
    if args.spectral:
        n_workers = 1  # librosa not great with multiprocessing

    print(f'Processing with {n_workers} workers...')
    start_time = time.time()

    if n_workers == 1:
        results = [process_file(fa) for fa in tqdm(file_args, desc='Processing')]
    else:
        with Pool(n_workers) as pool:
            results = list(tqdm(
                pool.imap(process_file, file_args),
                total=len(file_args),
                desc='Processing',
            ))

    elapsed = time.time() - start_time
    print(f'Processing took {elapsed:.1f}s')

    errors = [r for r in results if r is not None and 'error' in r]
    valid  = [r for r in results if r is not None and 'error' not in r]
    print(f'Valid: {len(valid)}, Errors: {len(errors)}')
    for e in errors[:3]:
        print(f'  Error: {e["error"][:100]}')

    # Separate by split, preserving original row index for audio_path lookup
    splits = {'train': [], 'validation': [], 'test': []}
    split_audio = {'train': [], 'validation': [], 'test': []}

    for i, (_, row) in enumerate(meta.iterrows()):
        if i >= len(results) or results[i] is None or 'error' in results[i]:
            continue
        split = row.get('split', 'train')
        splits[split].append(results[i])
        split_audio[split].append(audio_paths[i])

    # Process each split
    for split_name, split_data in splits.items():
        if not split_data:
            print(f'Skip {split_name}: no data')
            continue

        all_tokens      = [d['tokens']      for d in split_data]
        all_onset_times = [d['onset_times'] for d in split_data]
        all_continuous  = [d['continuous']  for d in split_data] if args.spectral else None

        # Drop files missing audio when spectral is enabled
        if all_continuous and any(c is None for c in all_continuous):
            paired = [
                (t, c, ot, ap)
                for t, c, ot, ap in zip(
                    all_tokens, all_continuous, all_onset_times,
                    split_audio[split_name],
                )
                if c is not None
            ]
            if paired:
                all_tokens, all_continuous, all_onset_times, split_audio[split_name] = (
                    list(zip(*paired))
                )
            else:
                all_continuous = None

        total_toks = sum(len(t) for t in all_tokens)
        print(f'\n{split_name}: {len(all_tokens)} files, {total_toks:,} total tokens')

        token_arr, cont_arr, window_times_arr, file_idx_arr = create_training_windows(
            all_tokens, all_continuous, args.seq_len, args.stride,
            all_onset_times=all_onset_times,
        )
        print(f'  Windows: {len(token_arr)} × seq_len={args.seq_len}')

        # Save token windows
        np.save(output_dir / f'{split_name}_tokens.npy', token_arr)

        # Save continuous spectral features (5-scalar, legacy)
        if cont_arr is not None:
            np.save(output_dir / f'{split_name}_continuous.npy', cont_arr)
            print(f'  Continuous shape: {cont_arr.shape}')

        # Save window onset times (always — needed for mel alignment)
        np.save(output_dir / f'{split_name}_window_times.npy', window_times_arr)

        # Mel spectrogram extraction
        if args.mel:
            print(f'  Computing mel patches ({args.mel_frames} frames × {args.n_mels} bins)...')
            mel_arr = extract_mel_windows(
                audio_paths     = list(split_audio[split_name]),
                file_idx_arr    = file_idx_arr,
                window_times_arr= window_times_arr,
                mel_frames      = args.mel_frames,
                n_mels          = args.n_mels,
            )
            np.save(output_dir / f'{split_name}_mel.npy', mel_arr)
            print(f'  Mel shape: {mel_arr.shape}, size: {mel_arr.nbytes / 1e9:.2f} GB')

    # Save metadata
    meta_out = {
        'vocab_size':      VOCAB_SIZE,
        'seq_len':         args.seq_len,
        'stride':          args.stride,
        'spectral':        args.spectral,
        'mel':             args.mel,
        'mel_frames':      args.mel_frames if args.mel else 0,
        'n_mels':          args.n_mels     if args.mel else 0,
        'continuous_dim':  CONTINUOUS_DIM  if args.spectral else 0,
        'tokens_per_event':TOKENS_PER_EVENT,
        'n_files':         len(valid),
        'n_errors':        len(errors),
        'splits':          {k: len(v) for k, v in splits.items()},
        'processing_time_s': elapsed,
    }
    with open(output_dir / 'meta.json', 'w') as f:
        json.dump(meta_out, f, indent=2)

    print(f'\nSaved to {output_dir}/')
    print(json.dumps(meta_out, indent=2))


if __name__ == '__main__':
    main()
