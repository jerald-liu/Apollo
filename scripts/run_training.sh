#!/bin/bash
# Apollo — Full training pipeline
# Run on GPU instance after setup_gpu.sh
#
# Downloads MAESTRO (MIDI-only or full w/ audio), preprocesses, and trains.
#
# Usage:
#   bash scripts/run_training.sh              # MIDI-only (no spectral)
#   bash scripts/run_training.sh --spectral   # With spectral features (needs full MAESTRO ~101GB)

set -e
source venv/bin/activate

SPECTRAL=false
CONFIG="configs/base.yaml"

for arg in "$@"; do
    case $arg in
        --spectral)  SPECTRAL=true ;;
        --large)     CONFIG="configs/large.yaml" ;;
    esac
done

echo "=== Apollo Training Pipeline ==="
echo "Config: $CONFIG"
echo "Spectral: $SPECTRAL"
echo ""

# --- Step 1: Download MAESTRO ---
mkdir -p data/raw

if [ "$SPECTRAL" = true ]; then
    echo "Downloading MAESTRO v3 (full, ~101GB)..."
    if [ ! -d "data/raw/maestro-v3.0.0" ] || [ ! -f "data/raw/maestro-v3.0.0/2004/MIDI-Unprocessed_Chamber3_MID--AUDIO_10_R3_2018_wav--1.wav" ]; then
        wget -q --show-progress -O data/raw/maestro-v3.0.0.zip \
            "https://storage.googleapis.com/magentadata/datasets/maestro/v3.0.0/maestro-v3.0.0.zip"
        cd data/raw && unzip -q -o maestro-v3.0.0.zip && cd ../..
    fi
    PREPROCESS_ARGS="--midi-dir data/raw/maestro-v3.0.0 --audio-dir data/raw/maestro-v3.0.0 --spectral"
else
    echo "Downloading MAESTRO v3 (MIDI-only, ~56MB)..."
    if [ ! -d "data/raw/maestro-v3.0.0" ]; then
        wget -q --show-progress -O data/raw/maestro-v3.0.0-midi.zip \
            "https://storage.googleapis.com/magentadata/datasets/maestro/v3.0.0/maestro-v3.0.0-midi.zip"
        cd data/raw && unzip -q -o maestro-v3.0.0-midi.zip && cd ../..
    fi
    PREPROCESS_ARGS="--midi-dir data/raw/maestro-v3.0.0"
fi

# --- Step 2: Preprocess ---
echo ""
echo "=== Preprocessing ==="
python scripts/preprocess.py $PREPROCESS_ARGS \
    --seq-len 512 --stride 256 --output-dir data/processed

# --- Step 3: Train ---
echo ""
echo "=== Training ==="

# Detect number of GPUs
NUM_GPUS=$(nvidia-smi -L 2>/dev/null | wc -l)
echo "GPUs detected: $NUM_GPUS"

if [ "$NUM_GPUS" -gt 1 ]; then
    echo "Using DDP with $NUM_GPUS GPUs"
    torchrun --nproc_per_node=$NUM_GPUS scripts/train.py --config $CONFIG
else
    python scripts/train.py --config $CONFIG
fi

echo ""
echo "=== Training complete ==="
echo "Models saved in: models/"
ls -la models/checkpoint_*.pt 2>/dev/null
