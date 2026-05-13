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

        # Rolling buffer of recent input events
        self.max_buffer_events = config.get("max_buffer_events", 64)
        self.event_buffer = deque(maxlen=self.max_buffer_events)
        self.last_note_time = time.time()

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

    def _stream_generate(self, prompt: torch.Tensor, n_gen: int):
        """Token-streaming generator: yields (event, timbre_row | None) as each
        complete event (TOKENS_PER_EVENT tokens) is decoded.  Sending starts
        after the first 5 tokens rather than waiting for the full sequence.
        """
        import torch.nn.functional as F
        tokens = prompt.clone()
        token_batch: list[int] = []

        for _ in range(n_gen):
            context = tokens[:, -self.model.max_seq_len:]
            with torch.no_grad():
                output = self.model(context, tokens_per_event=TOKENS_PER_EVENT)

            logits = output["logits"][:, -1, :] / self.temperature
            if self.top_k > 0:
                v, _ = torch.topk(logits, min(self.top_k, logits.size(-1)))
                logits[logits < v[:, [-1]]] = float("-inf")
            probs = F.softmax(logits, dim=-1)
            next_tok = torch.multinomial(probs, 1)
            tokens = torch.cat([tokens, next_tok], dim=1)

            tok_id = next_tok.item()
            if tok_id == TOKEN_OFFSETS["eos"]:
                break

            token_batch.append(tok_id)

            if len(token_batch) == TOKENS_PER_EVENT:
                events = tokens_to_events(token_batch)
                timbre_row = None
                if events and "timbre" in output:
                    # timbre at position of last token in this event
                    pos = tokens.shape[1] - prompt.shape[1] - 1
                    pos = min(pos, output["timbre"].shape[1] - 1)
                    if pos >= 0:
                        timbre_row = output["timbre"][0, pos].cpu().numpy()
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
        disp.map("/apollo/note", self.handle_note)
        disp.map("/apollo/pedal", self.handle_pedal)
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
