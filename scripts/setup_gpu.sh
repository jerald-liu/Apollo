#!/bin/bash
# Apollo — Cloud GPU Setup Script
# Run this on a fresh cloud GPU instance (Lambda, RunPod, vast.ai, etc.)
#
# Usage:
#   # Clone and setup:
#   git clone <your-repo-url> apollo && cd apollo
#   bash scripts/setup_gpu.sh
#
#   # Then preprocess and train:
#   bash scripts/run_training.sh

set -e

echo "=== Apollo GPU Setup ==="

# System packages
sudo apt-get update -q
sudo apt-get install -y -q ffmpeg libsndfile1

# Python environment
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip

# Core dependencies
pip install \
    torch>=2.0 \
    numpy \
    pretty_midi \
    mido \
    librosa \
    pandas \
    matplotlib \
    tqdm \
    pyyaml \
    wandb

echo "=== Setup complete ==="
echo "Activate with: source venv/bin/activate"
nvidia-smi 2>/dev/null || echo "(No NVIDIA GPU detected)"
