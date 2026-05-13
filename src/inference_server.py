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
        model_config = {
            "vocab_size": config.get("vocab_size", 380),
            "d_model": config.get("d_model", 384),
            "nhead": config.get("nhead", 6),
            "num_layers": config.get("num_layers", 6),
            "max_seq_len": config.get("max_seq_len", 512),
            "user_embed_dim": config.get("user_embed_dim", 0),
            "spectral_dim": config.get("spectral_dim", 21),
            "n_timbre_outputs": config.get("n_timbre_outputs", 5),
            "dropout": 0.0,  # no dropout at inference
        }

        model = ApolloModel(**model_config)

        checkpoint_path = PROJECT_ROOT / config.get("checkpoint", "models/checkpoint_best.pt")
        if checkpoint_path.exists():
            print(f"[Apollo] Loading checkpoint: {checkpoint_path}")
            state = torch.load(checkpoint_path, map_location=self.device, weights_only=True)
            # Handle checkpoints saved with 'model_state_dict' key
            state_dict = state["model_state_dict"] if "model_state_dict" in state else state
            # strict=False handles checkpoints trained without spectral/timbre heads
            missing, unexpected = model.load_state_dict(state_dict, strict=False)
            if missing:
                print(f"[Apollo] Note: {len(missing)} keys not in checkpoint "
                      f"(spectral/timbre heads will use random init)")
        else:
            print(f"[Apollo] WARNING: No checkpoint at {checkpoint_path}, using random weights")

        model = model.to(self.device)
        model.eval()
        return model

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

    def _generate_response(self):
        """Run model inference on the current event buffer and send results."""
        t_start = time.time()

        with self.lock:
            if len(self.event_buffer) < 2:
                return
            events = list(self.event_buffer)

        # Tokenize input events
        tokens = events_to_tokens(events)
        # Append SEP token to signal "now generate a response"
        tokens.append(TOKEN_OFFSETS["sep"])

        prompt = torch.tensor([tokens], dtype=torch.long, device=self.device)

        # Determine how many tokens to generate based on density
        # density 0.0 = ~1 event (5 tokens), density 1.0 = max_gen_tokens
        n_gen = max(5, int(self.max_gen_tokens * self.density))

        # Run inference
        try:
            gen_tokens, timbre_out = self.model.generate(
                prompt=prompt,
                max_new_tokens=n_gen,
                temperature=self.temperature,
                top_k=self.top_k,
                tokens_per_event=TOKENS_PER_EVENT,
            )
        except Exception as e:
            self.osc_client.send_message("/apollo/error", [str(e)])
            return

        # Extract only the newly generated tokens (after our prompt + SEP)
        prompt_len = len(tokens)
        new_tokens = gen_tokens[0, prompt_len:].cpu().tolist()

        # Decode generated tokens back to events
        gen_events = tokens_to_events(new_tokens)

        # Extract timbre predictions for the generated events
        # timbre_out shape: (1, N_new_tokens, 5)
        # We need per-event timbre, sampled every TOKENS_PER_EVENT steps
        timbre_values = None
        if timbre_out is not None:
            timbre_np = timbre_out[0].cpu().numpy()
            # Sample timbre at event boundaries (every TOKENS_PER_EVENT tokens)
            event_indices = list(range(0, len(timbre_np), TOKENS_PER_EVENT))
            timbre_values = timbre_np[event_indices[:len(gen_events)]]

        latency_ms = (time.time() - t_start) * 1000

        # Send generated events back to M4L
        for i, event in enumerate(gen_events):
            # Send note (apply velocity scaling)
            scaled_vel = event.velocity * 127 * self.velocity_scale
            self.osc_client.send_message("/apollo/gen/note", [
                event.pitch,
                int(np.clip(scaled_vel, 1, 127)),
                event.delta_time * 1000,  # convert to ms
                event.duration * 1000,    # convert to ms
                event.pedal,
            ])

            # Send timbral CCs
            if timbre_values is not None and i < len(timbre_values):
                timbre = timbre_values[i]  # [brightness, attack, richness, warmth, flux]

                # Send raw timbre for display
                self.osc_client.send_message("/apollo/gen/timbre",
                                             [float(v) for v in timbre])

                # Apply influence scaling + offsets, then send as MIDI CC
                for desc_idx, cc_num in self.cc_map.items():
                    val = timbre[desc_idx] * self.timbre_influence
                    if desc_idx < len(self.timbre_offsets):
                        val += self.timbre_offsets[desc_idx]
                    val = np.clip(val, 0.0, 1.0)
                    cc_val = int(val * 127)
                    self.osc_client.send_message("/apollo/gen/cc", [cc_num, cc_val])

        # Send status with latency
        self.osc_client.send_message("/apollo/status", ["ok", latency_ms])

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
