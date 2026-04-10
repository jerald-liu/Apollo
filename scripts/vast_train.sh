#!/bin/bash
# Apollo — vast.ai one-shot training script
#
# 1. Rent an A100 instance on vast.ai (PyTorch template, ~$1-2/hr)
# 2. SSH in and run:
#      git clone https://github.com/jerald-liu/apollo.git && cd apollo
#      bash scripts/vast_train.sh
#
# Expects preprocessed data uploaded to data/processed/ OR downloads + preprocesses MAESTRO.
# Total runtime: ~2 hours on A100 for base config (50K steps).

set -e

echo "=== Apollo Training on vast.ai ==="
nvidia-smi || { echo "No GPU detected!"; exit 1; }

# Install deps
pip install torch numpy pretty_midi mido pandas tqdm pyyaml 2>&1 | tail -1

# Check if preprocessed data exists, otherwise download and preprocess
if [ ! -f "data/processed/train_tokens.npy" ]; then
    echo "No preprocessed data found. Downloading MAESTRO and preprocessing..."
    mkdir -p data/raw
    wget -q --show-progress -O data/raw/maestro-v3.0.0-midi.zip \
        "https://storage.googleapis.com/magentadata/datasets/maestro/v3.0.0/maestro-v3.0.0-midi.zip"
    cd data/raw && unzip -q -o maestro-v3.0.0-midi.zip && cd ../..
    python scripts/preprocess.py --midi-dir data/raw/maestro-v3.0.0 --seq-len 512 --stride 256
else
    echo "Preprocessed data found."
fi

echo ""
echo "=== Starting training ==="
echo "Config: configs/base.yaml"
echo "Expected: ~2 hours on A100, ~50K steps"
echo ""

# Detect multi-GPU
NUM_GPUS=$(nvidia-smi -L 2>/dev/null | wc -l)
echo "GPUs: $NUM_GPUS"

if [ "$NUM_GPUS" -gt 1 ]; then
    torchrun --nproc_per_node=$NUM_GPUS scripts/train.py --config configs/base.yaml --spectral false
else
    python scripts/train.py --config configs/base.yaml --spectral false
fi

echo ""
echo "=== Done ==="
ls -lh models/checkpoint_*.pt
