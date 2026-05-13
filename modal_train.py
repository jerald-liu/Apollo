"""Apollo — Modal training infrastructure.

Provisions GPU compute, persistent data/checkpoint volumes, and runs
preprocessing and training as one-shot remote functions.

Usage:
    # First time: preprocess MAESTRO onto the volume (MIDI-only, ~56MB download)
    modal run modal_train.py --action preprocess

    # With full audio for spectral features (~101GB download, run on GPU instance)
    modal run modal_train.py --action preprocess --spectral

    # Train with base config (A100, ~6-8 hours, ~$5-15)
    modal run modal_train.py

    # Resume an interrupted run
    modal run modal_train.py --resume checkpoint_latest.pt

    # Use large config
    modal run modal_train.py --config configs/large.yaml

    # Download best checkpoint after training
    modal volume get apollo-checkpoints checkpoint_best.pt models/checkpoint_best.pt

Prerequisites:
    pip install modal
    modal setup   # authenticates via browser
"""

import modal
from pathlib import Path

# ---------------------------------------------------------------------------
# Image
# Two-layer pip install: torch (heavy, CUDA index) cached independently from
# lighter ML libs. Code injected at container startup via add_local_dir
# (copy=False default) — no image rebuild when src/scripts/configs change.
# ---------------------------------------------------------------------------

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg", "libsndfile1", "wget", "unzip")
    .pip_install(
        "torch==2.3.1",
        extra_index_url="https://download.pytorch.org/whl/cu121",
    )
    .pip_install(
        "numpy==1.26.4",
        "pretty_midi==0.2.10",
        "mido==1.3.2",
        "librosa==0.10.2",
        "tqdm==4.66.4",
        "PyYAML==6.0.1",
        "wandb==0.17.0",
    )
    .add_local_dir("src",     "/workspace/src")
    .add_local_dir("scripts", "/workspace/scripts")
    .add_local_dir("configs", "/workspace/configs")
    .env({"PYTHONPATH": "/workspace"})
)

# ---------------------------------------------------------------------------
# Volumes  (persist across runs; survive instance termination)
# ---------------------------------------------------------------------------

data_vol = modal.Volume.from_name("apollo-data", create_if_missing=True)
ckpt_vol = modal.Volume.from_name("apollo-checkpoints", create_if_missing=True)

DATA_DIR = "/data"
CKPT_DIR = "/checkpoints"

app = modal.App("apollo")


# ---------------------------------------------------------------------------
# Preprocess — CPU-heavy, no GPU needed
# Downloads MAESTRO and tokenizes it onto the persistent data volume.
# Safe to re-run: skips download if raw data already present.
# ---------------------------------------------------------------------------

@app.function(
    image=image,
    cpu=8.0,
    memory=32768,
    timeout=60 * 60 * 6,
    volumes={DATA_DIR: data_vol},
)
def preprocess(spectral: bool = False):
    import subprocess

    raw_dir = f"{DATA_DIR}/raw/maestro-v3.0.0"

    if not Path(raw_dir).exists():
        Path(f"{DATA_DIR}/raw").mkdir(parents=True, exist_ok=True)
        url = (
            "https://storage.googleapis.com/magentadata/datasets/maestro/v3.0.0/maestro-v3.0.0.zip"
            if spectral
            else "https://storage.googleapis.com/magentadata/datasets/maestro/v3.0.0/maestro-v3.0.0-midi.zip"
        )
        print(f"Downloading MAESTRO ({'full ~101GB' if spectral else 'MIDI-only ~56MB'})...")
        subprocess.run(
            ["wget", "-q", "--show-progress", "-O", f"{DATA_DIR}/raw/maestro.zip", url],
            check=True,
        )
        subprocess.run(
            ["unzip", "-q", "-o", f"{DATA_DIR}/raw/maestro.zip", "-d", f"{DATA_DIR}/raw/"],
            check=True,
        )

    args = [
        "python", "/workspace/scripts/preprocess.py",
        "--midi-dir", raw_dir,
        "--output-dir", f"{DATA_DIR}/processed",
    ]
    if spectral:
        args += ["--audio-dir", raw_dir, "--spectral"]

    subprocess.run(args, cwd="/workspace", check=True)
    data_vol.commit()
    print(f"Done. Preprocessed data at {DATA_DIR}/processed/")


# ---------------------------------------------------------------------------
# Train — GPU function
# ---------------------------------------------------------------------------

@app.function(
    image=image,
    gpu="A100",
    timeout=60 * 60 * 12,
    volumes={
        DATA_DIR: data_vol,
        CKPT_DIR: ckpt_vol,
    },
)
def train(config: str = "configs/base.yaml", resume: str = None):
    import subprocess

    args = [
        "python", "/workspace/scripts/train.py",
        "--config", f"/workspace/{config}",
        "--data-dir", f"{DATA_DIR}/processed",
        "--output-dir", CKPT_DIR,
    ]
    if resume:
        args += ["--resume", f"{CKPT_DIR}/{resume}"]

    subprocess.run(args, cwd="/workspace", check=True)
    ckpt_vol.commit()
    print(f"Done. Checkpoints at {CKPT_DIR}/")


# ---------------------------------------------------------------------------
# Local entrypoint
# ---------------------------------------------------------------------------

@app.local_entrypoint()
def main(
    action: str = "train",
    config: str = "configs/base.yaml",
    spectral: bool = False,
    resume: str = None,
):
    if action == "preprocess":
        preprocess.remote(spectral=spectral)
    elif action == "train":
        train.remote(config=config, resume=resume)
    else:
        raise ValueError(f"Unknown action '{action}'. Use 'preprocess' or 'train'.")
