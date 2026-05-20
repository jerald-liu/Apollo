"""apollo/scripts/generate.py — autoregressive inference CLI.

INFER-01: Accepts checkpoint + call.mid + call.wav, emits response.mid.
INFER-02: --max-tokens flag.
INFER-03: --temperature, --top-k flags.
INFER-04: --n flag for batch sampling.

Decisions:
- D-13: BPM read from call MIDI via pretty_midi.PrettyMIDI(path).estimate_tempo()
- D-14: defaults temperature=0.8, top-k=10
- D-15: stop on EOS OR max_tokens=24 (default), whichever first
- D-16: invalid tokens skipped (decode_tokens range errors caught, partial groups dropped)
- D-17: output as response_NNN.mid alongside call.mid; non-destructive (next available index)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pretty_midi
import torch

from apollo.ingest.audio import MelExtractor
from apollo.ingest.midi import load_notes
from apollo.model import ApolloModel, BOS, EOS, SEP, get_device
from apollo.model.train import load_checkpoint
from apollo.tokenizer.decoder import decode_tokens
from apollo.tokenizer.encoder import Tokenizer
from apollo.tokenizer.vocab import Vocab


def _next_response_path(pair_dir: Path) -> Path:
    """D-17: find next available response_NNN.mid index; never overwrite."""
    idx = 1
    while True:
        candidate = pair_dir / f"response_{idx:03d}.mid"
        if not candidate.exists():
            return candidate
        idx += 1


def _strip_specials(ids: list[int]) -> list[int]:
    """Remove any BOS/SEP/EOS from generated token list before decode_tokens."""
    return [t for t in ids if t not in (BOS, SEP, EOS)]


def _decode_with_invalid_skip(ids: list[int], vocab: Vocab, tempo_bpm: float):
    """D-16: decode tokens, skipping any group that raises ValueError.

    Returns (notes, n_invalid_groups).
    """
    ids = ids[: (len(ids) // 4) * 4]
    if not ids:
        return [], 0
    try:
        return decode_tokens(ids, vocab, tempo_bpm=tempo_bpm), 0
    except ValueError:
        notes = []
        n_invalid = 0
        for i in range(0, len(ids), 4):
            group = ids[i : i + 4]
            try:
                notes.extend(decode_tokens(group, vocab, tempo_bpm=tempo_bpm))
            except ValueError:
                n_invalid += 1
        return notes, n_invalid


def _sample_one_response(
    model: ApolloModel,
    prefix_ids: list[int],
    mel_batch: torch.Tensor,
    device: torch.device,
    max_tokens: int,
    temperature: float,
    top_k: int,
) -> list[int]:
    """Autoregressive sampling loop. Returns generated token IDs (no BOS/SEP)."""
    generated: list[int] = []
    for _ in range(max_tokens):
        ids_tensor = torch.tensor(
            [prefix_ids + generated], dtype=torch.long, device=device
        )  # (1, T)
        with torch.no_grad():
            logits = model(ids_tensor, mel_batch, key_padding_mask=None)
        # logits: (1, T, 256); next-token logit is at the final position
        next_logit = logits[0, -1, :] / max(temperature, 1e-8)  # (256,)
        top_k_vals, top_k_ids = torch.topk(next_logit, k=min(top_k, next_logit.numel()))
        probs = torch.softmax(top_k_vals, dim=-1)
        chosen = torch.multinomial(probs, num_samples=1)
        next_id = int(top_k_ids[chosen].item())
        if next_id == EOS:
            break
        generated.append(next_id)
    return generated


def _write_response_midi(notes, out_path: Path, tempo_bpm: float) -> None:
    """Write Notes to MIDI via pretty_midi."""
    pm = pretty_midi.PrettyMIDI(initial_tempo=tempo_bpm)
    inst = pretty_midi.Instrument(program=0)
    for note in notes:
        inst.notes.append(
            pretty_midi.Note(
                velocity=int(note.velocity),
                pitch=int(note.pitch),
                start=float(note.start),
                end=float(note.end),
            )
        )
    pm.instruments.append(inst)
    pm.write(str(out_path))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate a MIDI response to an Apollo call/wav pair."
    )
    parser.add_argument("checkpoint", help="Path to .pt checkpoint file")
    parser.add_argument("call_mid", help="Path to call.mid")
    parser.add_argument("call_wav", help="Path to call.wav")
    parser.add_argument(
        "--n", type=int, default=1,
        help="Number of responses to generate (INFER-04, default 1)",
    )
    parser.add_argument(
        "--temperature", type=float, default=0.8,
        help="Sampling temperature (D-14, default 0.8)",
    )
    parser.add_argument(
        "--top-k", type=int, default=10,
        help="Top-k sampling (D-14, default 10)",
    )
    parser.add_argument(
        "--max-tokens", type=int, default=24,
        help="Max response tokens; 6 notes * 4 tokens (D-15, default 24)",
    )
    args = parser.parse_args(argv)

    try:
        call_mid_path = Path(args.call_mid)
        call_wav_path = Path(args.call_wav)
        if not call_mid_path.exists():
            print(f"ERROR: call.mid not found: {call_mid_path}", file=sys.stderr)
            return 1
        if not call_wav_path.exists():
            print(f"ERROR: call.wav not found: {call_wav_path}", file=sys.stderr)
            return 1

        # 1. Load checkpoint and reconstruct model (Phase 2 5-key format)
        ckpt = load_checkpoint(args.checkpoint, map_location="cpu")
        model = ApolloModel(**ckpt["model_config"])
        model.load_state_dict(ckpt["model_state_dict"])
        # mel_enc is a submodule of ApolloModel (Phase 2 D-23)
        model.mel_enc.load_state_dict(ckpt["mel_encoder_state_dict"])
        device = get_device()
        model = model.to(device)
        model.eval()

        # 2. BPM from call MIDI (D-13; load_notes does NOT return BPM)
        call_bpm = float(pretty_midi.PrettyMIDI(str(call_mid_path)).estimate_tempo())

        # 3. Encode call tokens for the inference prefix
        vocab = Vocab()
        call_notes = load_notes(
            str(call_mid_path), str(call_mid_path.parent), tempo_bpm=call_bpm
        )
        tokenizer = Tokenizer(vocab, tempo_bpm=call_bpm)
        # encode() returns raw note tokens (no BOS/EOS — encoder.py is note-only)
        call_token_ids = tokenizer.encode(call_notes)

        # 4. Mel extraction from call.wav -> (96,128) -> (1,1,96,128)
        mx = MelExtractor()
        mel = mx(str(call_wav_path), str(call_wav_path.parent))
        mel_batch = mel.unsqueeze(0).unsqueeze(0).to(device)  # (1,1,96,128)

        # 5. Inference prefix: [BOS, call_tokens..., SEP] (matches training packer layout)
        prefix_ids = [BOS] + call_token_ids + [SEP]

        # 6. Sample N responses
        pair_dir = call_mid_path.parent
        for _sample_idx in range(args.n):
            generated = _sample_one_response(
                model=model,
                prefix_ids=prefix_ids,
                mel_batch=mel_batch,
                device=device,
                max_tokens=args.max_tokens,
                temperature=args.temperature,
                top_k=args.top_k,
            )
            response_ids = _strip_specials(generated)
            notes, n_invalid = _decode_with_invalid_skip(
                response_ids, vocab, tempo_bpm=call_bpm
            )
            out_path = _next_response_path(pair_dir)
            _write_response_midi(notes, out_path, tempo_bpm=call_bpm)
            print(
                f"Generated {len(notes)} note(s), {n_invalid} invalid group(s) "
                f"skipped -> {out_path}"
            )

        return 0

    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"UNEXPECTED ERROR: {e!r}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
