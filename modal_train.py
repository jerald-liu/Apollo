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
        "pandas==2.2.2",
        "pretty_midi==0.2.10",
        "mido==1.3.2",
        "librosa==0.10.2",
        "tqdm==4.66.4",
        "PyYAML==6.0.1",
        "wandb==0.17.0",
    )
    .env({"PYTHONPATH": "/workspace", "PYTHONUNBUFFERED": "1"})
    # add_local_dir must be last — no build steps allowed after it
    .add_local_dir("src",     "/workspace/src")
    .add_local_dir("scripts", "/workspace/scripts")
    .add_local_dir("configs", "/workspace/configs")
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
    timeout=60 * 60 * 12,  # 12h — mel extraction on full MAESTRO needs headroom
    volumes={DATA_DIR: data_vol},
)
def preprocess(spectral: bool = False, mel: bool = False):
    import subprocess

    raw_dir = f"{DATA_DIR}/raw/maestro-v3.0.0"
    need_audio = spectral or mel

    # Determine whether we need to (re-)download.
    # Audio (.wav) files are only present in the full zip, not the MIDI-only zip.
    # If audio is required and no .wav exists, download even if the directory exists.
    has_audio = need_audio and bool(list(Path(raw_dir).rglob("*.wav"))) if Path(raw_dir).exists() else False
    needs_download = not Path(raw_dir).exists() or (need_audio and not has_audio)

    if needs_download:
        Path(f"{DATA_DIR}/raw").mkdir(parents=True, exist_ok=True)
        url = (
            "https://storage.googleapis.com/magentadata/datasets/maestro/v3.0.0/maestro-v3.0.0.zip"
            if need_audio
            else "https://storage.googleapis.com/magentadata/datasets/maestro/v3.0.0/maestro-v3.0.0-midi.zip"
        )
        print(f"Downloading MAESTRO ({'full ~101GB' if need_audio else 'MIDI-only ~56MB'})...")
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
    if mel:
        args += ["--audio-dir", raw_dir, "--mel"]

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
    import subprocess, yaml as _yaml

    # Derive the volume-mounted data path from the config's data_dir field.
    # Config says e.g. "data/processed_streaming"; on Modal that lives at
    # /data/processed_streaming  (DATA_DIR = /data, strip leading "data/").
    with open(f"/workspace/{config}") as _f:
        _cfg = _yaml.safe_load(_f)
    _local_data_dir = _cfg.get("data_dir", "data/processed")   # e.g. "data/processed_streaming"
    _sub = _local_data_dir.split("/", 1)[-1]                    # "processed_streaming"
    _remote_data_dir = f"{DATA_DIR}/{_sub}"                     # "/data/processed_streaming"

    _run_name = _cfg.get("run_name", "apollo_run")
    _run_ckpt_dir = f"{CKPT_DIR}/{_run_name}"

    import subprocess as _sp
    _sp.run(["mkdir", "-p", _run_ckpt_dir], check=True)

    args = [
        "python", "/workspace/scripts/train.py",
        "--config", f"/workspace/{config}",
        "--data-dir", _remote_data_dir,
        "--output-dir", _run_ckpt_dir,
    ]
    if resume:
        args += ["--resume", f"{_run_ckpt_dir}/{resume}"]

    subprocess.run(args, cwd="/workspace", check=True)
    ckpt_vol.commit()
    print(f"Done. Checkpoints at {_run_ckpt_dir}/")


# ---------------------------------------------------------------------------
# Local entrypoint
# ---------------------------------------------------------------------------

@app.local_entrypoint()
def main(
    action: str = "train",
    config: str = "configs/base.yaml",
    spectral: bool = False,
    mel: bool = False,
    resume: str = None,
):
    with modal.enable_output():
        if action == "preprocess":
            preprocess.remote(spectral=spectral, mel=mel)
        elif action == "train":
            train.remote(config=config, resume=resume)
        else:
            raise ValueError(f"Unknown action '{action}'. Use 'preprocess' or 'train'.")
