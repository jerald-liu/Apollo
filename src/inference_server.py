"""Apollo real-time inference server — OSC bridge for Max4Live.

Receives MIDI events from the M4L device via OSC, runs model inference,
and sends generated events + timbral CCs back.

Usage:
    python src/inference_server.py --config configs/inference.yaml
"""

import argparse
import sys
import time
import threading
from collections import deque
from pathlib import Path

import numpy as np
import torch
import yaml
from pythonosc import dispatcher, osc_server, udp_client

# Add project root to path so imports work when run from any directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from model import ApolloModel
from representation import (
    ApolloEvent,
    TOKEN_OFFSETS,
    TOKENS_PER_EVENT,
    CONTINUOUS_DIM,
    events_to_tokens,
    events_to_continuous,
    tokens_to_events,
)
from streaming_representation import (
    OFFSETS as STREAM_OFFSETS,
    VOCAB_SIZE as STREAM_VOCAB_SIZE,
    TOKENS_PER_NOTE_ON,
    TOKENS_PER_NOTE_OFF,
    MEDIAN_DURATION_S,
    StreamNoteOn,
    StreamNoteOff,
    encode_note_on,
    encode_note_off,
    streaming_tokens_to_events,
)


class ApolloInferenceServer:
    """OSC server wrapping ApolloModel for real-time generation."""

    def __init__(self, config: dict):
        self.config = config

        # Generation parameters (updated via OSC)
        self.temperature = config.get("temperature", 0.9)
        self.top_k = config.get("top_k", 50)
        self.density = config.get("density", 0.5)
        self.timbre_influence = config.get("timbre_influence", 0.7)
        self.bypassed = False

        # Timbral offsets from M4L UI (-1 to +1)
        self.timbre_offsets = [0.0, 0.0, 0.0]  # brightness, attack, richness

        # Streaming mode: use note_on/note_off split (immediate dispatch)
        # vs legacy: wait for full event with duration before dispatching
        self.streaming_mode = config.get("streaming_mode", True)

        # Rolling buffer of recent input tokens (streaming) or events (legacy)
        self.max_buffer_events = config.get("max_buffer_events", 64)
        self.event_buffer = deque(maxlen=self.max_buffer_events)  # legacy: ApolloEvents
        self.token_buffer  = deque(maxlen=self.max_buffer_events * 5)  # streaming: raw tokens
        self.last_note_time = time.time()

        # Streaming: track pending note-ons for latency measurement and note_off matching
        # {pitch: (onset_wall_time, note_on_token_index)}
        self._pending_note_ons: dict = {}
        self._stream_prev_time: float = 0.0   # wall-clock time of last streamed event

        # Lock for thread-safe buffer access
        self.lock = threading.Lock()

        # OSC client for sending responses back to M4L
        self.osc_client = udp_client.SimpleUDPClient(
            config.get("m4l_host", "127.0.0.1"),
            config.get("m4l_port", 7400),
        )

        # Load model
        self.device = self._resolve_device(config.get("device", "auto"))
        self.model = self._load_model(config)
        self._warmup()

        # CC mapping: timbral descriptor index -> MIDI CC number
        self.cc_map = {
            0: 74,  # brightness -> Filter Cutoff
            1: 73,  # attack -> Attack Time
            2: 71,  # richness -> Resonance
        }

        # Velocity scaling (from M4L UI)
        self.velocity_scale = config.get("velocity_scale", 1.0)

        # Max tokens to generate per input event
        self.max_gen_tokens = config.get("max_gen_tokens", 50)

        print(f"[Apollo] Server ready on {config.get('device', 'auto')} "
              f"({self.device}), listening on :{config.get('listen_port', 7401)}")

    def _resolve_device(self, device_str: str) -> torch.device:
        if device_str == "auto":
            if torch.backends.mps.is_available():
                return torch.device("mps")
            elif torch.cuda.is_available():
                return torch.device("cuda")
            return torch.device("cpu")
        return torch.device(device_str)

    def _load_model(self, config: dict) -> ApolloModel:
        checkpoint_path = PROJECT_ROOT / config.get("checkpoint", "models/checkpoint_best.pt")

        if checkpoint_path.exists():
            print(f"[Apollo] Loading checkpoint: {checkpoint_path}")
            ckpt = torch.load(checkpoint_path, map_location=self.device, weights_only=False)
            # Prefer architecture from checkpoint — avoids config mismatch
            saved_cfg = ckpt.get("config", {})
            model_config = {
                "vocab_size":       saved_cfg.get("vocab_size",        config.get("vocab_size", 380)),
                "d_model":          saved_cfg.get("d_model",            config.get("d_model", 384)),
                "nhead":            saved_cfg.get("nhead",              config.get("nhead", 6)),
                "num_layers":       saved_cfg.get("num_layers",         config.get("num_layers", 6)),
                "max_seq_len":      saved_cfg.get("max_seq_len",        config.get("max_seq_len", 512)),
                "user_embed_dim":   saved_cfg.get("user_embed_dim",     0),
                "spectral_dim":     saved_cfg.get("spectral_dim", 0) if saved_cfg.get("spectral") else 0,
                "n_timbre_outputs": saved_cfg.get("n_timbre_outputs", 0) if saved_cfg.get("spectral") else 0,
                "dropout": 0.0,
            }
            step = ckpt.get("step", 0)
            val_loss = ckpt.get("best_val_loss", float("inf"))
            print(f"[Apollo] step={step:,}  best_val_loss={val_loss:.4f}  "
                  f"d_model={model_config['d_model']}  layers={model_config['num_layers']}")

            model = ApolloModel(**model_config)
            model.load_state_dict(ckpt["model_state_dict"])
        else:
            print(f"[Apollo] WARNING: No checkpoint at {checkpoint_path}, using random weights")
            model_config = {
                "vocab_size": 380, "d_model": config.get("d_model", 384),
                "nhead": config.get("nhead", 6), "num_layers": config.get("num_layers", 6),
                "max_seq_len": config.get("max_seq_len", 512),
                "user_embed_dim": 0, "spectral_dim": 0, "n_timbre_outputs": 0, "dropout": 0.0,
            }
            model = ApolloModel(**model_config)

        model = model.to(self.device)
        model.eval()
        return model

    def _warmup(self):
        """Run a dummy forward pass to trigger MPS/CUDA JIT compilation.
        Eliminates the ~280ms cold-start penalty on the first real inference call.
        """
        import time
        t = time.perf_counter()
        dummy = torch.zeros(1, 32, dtype=torch.long, device=self.device)
        with torch.no_grad():
            self.model(dummy, tokens_per_event=TOKENS_PER_EVENT)
        if self.device.type == "mps":
            torch.mps.synchronize()
        elapsed = (time.perf_counter() - t) * 1000
        print(f"[Apollo] Warmup complete ({elapsed:.0f}ms) — inference ready")

    # --- OSC Handlers ---

    def handle_note(self, address, *args):
        """Handle /apollo/note [pitch, velocity, deltaTime, duration, pedal]."""
        if self.bypassed or len(args) < 5:
            return

        pitch, velocity, delta_time, duration, pedal = args[:5]
        event = ApolloEvent(
            pitch=int(pitch),
            velocity=float(velocity),
            delta_time=float(delta_time),
            duration=float(duration),
            pedal=int(pedal),
        )

        with self.lock:
            self.event_buffer.append(event)
            self.last_note_time = time.time()

        # Run generation in a separate thread to avoid blocking the OSC server
        threading.Thread(target=self._generate_response, daemon=True).start()

    def handle_note_on(self, address, *args):
        """Handle /apollo/note_on [pitch, velocity] — emitted immediately on keypress.

        This is the streaming-mode handler. The note_on triplet is added to the
        token buffer right away; no waiting for key release.  delta_time is
        computed from wall-clock so the caller doesn't need to track it.
        """
        if self.bypassed or len(args) < 2:
            return

        pitch    = int(args[0])
        velocity = float(args[1]) / 127.0  # normalise if raw MIDI velocity

        now = time.time()
        with self.lock:
            delta = now - self._stream_prev_time
            self._stream_prev_time = now
            self._pending_note_ons[pitch] = now

            ev     = StreamNoteOn(pitch=pitch, velocity=velocity, delta_time=delta)
            tokens = encode_note_on(ev)        # 3 tokens: [time_shift, note_on, velocity]
            self.token_buffer.extend(tokens)
            self.last_note_time = now

        threading.Thread(target=self._generate_response_streaming, daemon=True).start()

    def handle_note_off(self, address, *args):
        """Handle /apollo/note_off [pitch] — emitted on key release.

        Adds the note_off 2-token pair to the token buffer.  No generation is
        triggered — note_offs are context for the model but the note_on already
        triggered generation.
        """
        if self.bypassed or len(args) < 1:
            return

        pitch = int(args[0])
        now   = time.time()

        with self.lock:
            delta = now - self._stream_prev_time
            self._stream_prev_time = now
            self._pending_note_ons.pop(pitch, None)

            ev     = StreamNoteOff(pitch=pitch, delta_time=delta)
            tokens = encode_note_off(ev)       # 2 tokens: [time_shift, note_off]
            self.token_buffer.extend(tokens)

    def handle_pedal(self, address, *args):
        """Handle /apollo/pedal [value]."""
        if args:
            # Update pedal state on the most recent event in buffer
            with self.lock:
                if self.event_buffer:
                    self.event_buffer[-1].pedal = int(args[0])

    def handle_config(self, address, *args):
        """Handle /apollo/config [temperature, topK, density, timbreInfluence]."""
        if len(args) >= 4:
            self.temperature = float(args[0])
            self.top_k = int(args[1])
            self.density = float(args[2])
            self.timbre_influence = float(args[3])

    def handle_transport(self, address, *args):
        """Handle /apollo/transport [playing, tempo, timeSigNum, timeSigDen]."""
        # Stored for future use (tempo-aware generation)
        pass

    def handle_model_load(self, address, *args):
        """Handle /apollo/model/load [name]."""
        if args:
            model_name = str(args[0])
            config_path = PROJECT_ROOT / "configs" / f"{model_name}.yaml"
            if config_path.exists():
                with open(config_path) as f:
                    new_config = yaml.safe_load(f)
                # Merge model params into current config
                for key in ["d_model", "nhead", "num_layers", "max_seq_len",
                            "spectral_dim", "n_timbre_outputs"]:
                    if key in new_config:
                        self.config[key] = new_config[key]
                self.model = self._load_model(self.config)
                self.osc_client.send_message("/apollo/status", ["model_loaded", 0.0])
            else:
                self.osc_client.send_message("/apollo/error",
                                             [f"Config not found: {model_name}"])

    def handle_timbre_offset(self, address, *args):
        """Handle /apollo/timbre/offset [brightness, attack, richness]."""
        if len(args) >= 3:
            self.timbre_offsets = [float(args[0]), float(args[1]), float(args[2])]

    def handle_bypass(self, address, *args):
        """Handle /apollo/bypass [state]."""
        if args:
            self.bypassed = bool(int(args[0]))

    def handle_cc_map(self, address, *args):
        """Handle /apollo/cc_map [brightness_cc, attack_cc, richness_cc]."""
        if len(args) >= 3:
            self.cc_map = {
                0: int(args[0]),  # brightness
                1: int(args[1]),  # attack
                2: int(args[2]),  # richness
            }

    def handle_velocity_scale(self, address, *args):
        """Handle /apollo/velocity_scale [scale]."""
        if args:
            self.velocity_scale = float(args[0])

    def handle_ping(self, address, *args):
        """Handle /apollo/ping — respond with pong."""
        self.osc_client.send_message("/apollo/pong", [])

    # --- Generation ---

    def _generate_response_streaming(self):
        """Run inference from the streaming token buffer.

        Uses the token_buffer (streaming note-on/note-off tokens) directly as
        the model prompt.  Generation output is decoded back to note events and
        sent via OSC.  Requires a model trained on streaming_representation vocab.
        """
        t_start = time.perf_counter()

        with self.lock:
            if len(self.token_buffer) < TOKENS_PER_NOTE_ON:
                return
            tokens = [STREAM_OFFSETS['bos']] + list(self.token_buffer)

        prompt = torch.tensor([tokens], dtype=torch.long, device=self.device)
        n_gen  = max(TOKENS_PER_NOTE_ON, int(self.max_gen_tokens * self.density))

        first_event = True
        token_acc: list[int] = []

        try:
            for tok_id, output in self._stream_generate_raw(prompt, n_gen):
                token_acc.append(tok_id)

                # Decode eagerly: note_on completes after 3 tokens (ts, pitch, vel)
                # note_off completes after 2 tokens (ts, pitch_off)
                decoded = False
                if len(token_acc) >= 3:
                    notes = streaming_tokens_to_events(token_acc)
                    if notes:
                        for n in notes:
                            if first_event:
                                ttfe = (time.perf_counter() - t_start) * 1000
                                self.osc_client.send_message("/apollo/status", ["ok", ttfe])
                                first_event = False
                            vel = int(np.clip(n['velocity'] * 127 * self.velocity_scale, 1, 127))
                            dur = (n.get('offset', n['onset'] + MEDIAN_DURATION_S) - n['onset']) * 1000
                            self.osc_client.send_message("/apollo/gen/note", [
                                n['pitch'], vel, 0.0, dur, 0,
                            ])
                        token_acc = []

        except Exception as e:
            self.osc_client.send_message("/apollo/error", [str(e)])

    def _stream_generate_raw(self, prompt: torch.Tensor, n_gen: int):
        """Low-level token generator — yields (tok_id, output) one token at a time."""
        import torch.nn.functional as F

        with torch.no_grad():
            output = self.model(prompt, tokens_per_event=TOKENS_PER_EVENT,
                                return_past_kvs=True, position_offset=0)
        past_kvs = output['past_kvs']
        tokens   = prompt.clone()
        offset   = prompt.shape[1]

        for _ in range(n_gen):
            last = tokens[:, -1:]
            with torch.no_grad():
                output = self.model(last, past_kvs=past_kvs,
                                    return_past_kvs=True, position_offset=offset)
            past_kvs = output['past_kvs']
            offset  += 1

            logits   = output['logits'][:, -1, :] / self.temperature
            if self.top_k > 0:
                v, _ = torch.topk(logits, min(self.top_k, logits.size(-1)))
                logits[logits < v[:, [-1]]] = float('-inf')
            probs    = torch.softmax(logits, dim=-1)
            next_tok = torch.multinomial(probs, 1)
            tokens   = torch.cat([tokens, next_tok], dim=1)

            tok_id = next_tok.item()
            if tok_id in (STREAM_OFFSETS['eos'], TOKEN_OFFSETS['eos']):
                break
            yield tok_id, output

    def _stream_generate(self, prompt: torch.Tensor, n_gen: int):
        """Token-streaming generator with KV-cache (O(T) per step after prefill).

        Yields (event | None, timbre_row | None) for each decoded event.
        """
        import torch.nn.functional as F

        # ── Prefill ───────────────────────────────────────────────────────
        with torch.no_grad():
            output = self.model(
                prompt,
                tokens_per_event=TOKENS_PER_EVENT,
                return_past_kvs=True,
                position_offset=0,
            )
        past_kvs = output['past_kvs']
        tokens   = prompt.clone()
        offset   = prompt.shape[1]
        token_batch: list[int] = []

        # ── Decode ────────────────────────────────────────────────────────
        for _ in range(n_gen):
            last = tokens[:, -1:]

            with torch.no_grad():
                output = self.model(
                    last,
                    past_kvs=past_kvs,
                    return_past_kvs=True,
                    position_offset=offset,
                )
            past_kvs = output['past_kvs']
            offset  += 1

            logits = output['logits'][:, -1, :] / self.temperature
            if self.top_k > 0:
                v, _ = torch.topk(logits, min(self.top_k, logits.size(-1)))
                logits[logits < v[:, [-1]]] = float('-inf')

            probs   = F.softmax(logits, dim=-1)
            next_tok = torch.multinomial(probs, 1)
            tokens   = torch.cat([tokens, next_tok], dim=1)

            tok_id = next_tok.item()
            if tok_id == TOKEN_OFFSETS['eos']:
                break

            token_batch.append(tok_id)

            if len(token_batch) == TOKENS_PER_EVENT:
                events    = tokens_to_events(token_batch)
                timbre_row = None
                if events and 'timbre' in output:
                    timbre_row = output['timbre'][0, 0].cpu().numpy()
                yield (events[0] if events else None), timbre_row
                token_batch = []

    def _generate_response(self):
        """Run streaming inference and send each event to M4L as it's ready."""
        t_start = time.perf_counter()

        with self.lock:
            if len(self.event_buffer) < 2:
                return
            events = list(self.event_buffer)

        tokens = events_to_tokens(events)
        # Strip trailing EOS — model was trained on sequences without EOS at the
        # context boundary, and SEP was never in training data, so just let the
        # model continue naturally after the last event.
        while tokens and tokens[-1] in (TOKEN_OFFSETS["eos"], TOKEN_OFFSETS["sep"]):
            tokens = tokens[:-1]
        prompt = torch.tensor([tokens], dtype=torch.long, device=self.device)

        n_gen = max(TOKENS_PER_EVENT, int(self.max_gen_tokens * self.density))

        first_event = True
        try:
            for event, timbre_row in self._stream_generate(prompt, n_gen):
                if event is None:
                    continue

                if first_event:
                    ttfe_ms = (time.perf_counter() - t_start) * 1000
                    self.osc_client.send_message("/apollo/status", ["ok", ttfe_ms])
                    first_event = False

                scaled_vel = event.velocity * 127 * self.velocity_scale
                self.osc_client.send_message("/apollo/gen/note", [
                    event.pitch,
                    int(np.clip(scaled_vel, 1, 127)),
                    event.delta_time * 1000,
                    event.duration * 1000,
                    event.pedal,
                ])

                if timbre_row is not None:
                    self.osc_client.send_message("/apollo/gen/timbre",
                                                 [float(v) for v in timbre_row])
                    for desc_idx, cc_num in self.cc_map.items():
                        val = timbre_row[desc_idx] * self.timbre_influence
                        if desc_idx < len(self.timbre_offsets):
                            val += self.timbre_offsets[desc_idx]
                        cc_val = int(np.clip(val, 0.0, 1.0) * 127)
                        self.osc_client.send_message("/apollo/gen/cc", [cc_num, cc_val])

        except Exception as e:
            self.osc_client.send_message("/apollo/error", [str(e)])

    # --- Server Lifecycle ---

    def start(self):
        """Start the OSC server."""
        disp = dispatcher.Dispatcher()
        disp.map("/apollo/note",     self.handle_note)      # legacy: full event w/ duration
        disp.map("/apollo/note_on",  self.handle_note_on)   # streaming: immediate on keypress
        disp.map("/apollo/note_off", self.handle_note_off)  # streaming: on key release
        disp.map("/apollo/pedal",    self.handle_pedal)
        disp.map("/apollo/config", self.handle_config)
        disp.map("/apollo/transport", self.handle_transport)
        disp.map("/apollo/model/load", self.handle_model_load)
        disp.map("/apollo/timbre/offset", self.handle_timbre_offset)
        disp.map("/apollo/bypass", self.handle_bypass)
        disp.map("/apollo/cc_map", self.handle_cc_map)
        disp.map("/apollo/velocity_scale", self.handle_velocity_scale)
        disp.map("/apollo/ping", self.handle_ping)

        listen_port = self.config.get("listen_port", 7401)
        server = osc_server.ThreadingOSCUDPServer(
            ("0.0.0.0", listen_port), disp
        )

        print(f"[Apollo] Inference server listening on port {listen_port}")
        print(f"[Apollo] Sending responses to port {self.config.get('m4l_port', 7400)}")
        print("[Apollo] Press Ctrl+C to stop")

        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\n[Apollo] Shutting down...")
            server.shutdown()


def main():
    parser = argparse.ArgumentParser(description="Apollo real-time inference server")
    parser.add_argument("--config", type=str, default="configs/inference.yaml",
                        help="Path to inference config YAML")
    args = parser.parse_args()

    config_path = PROJECT_ROOT / args.config
    if config_path.exists():
        with open(config_path) as f:
            config = yaml.safe_load(f)
    else:
        print(f"[Apollo] Config not found at {config_path}, using defaults")
        config = {}

    server = ApolloInferenceServer(config)
    server.start()


if __name__ == "__main__":
    main()
