FROM pytorch/pytorch:2.3.0-cuda12.1-cudnn8-runtime

WORKDIR /workspace

# librosa needs ffmpeg + libsndfile; wget/unzip for dataset download on GPU instance
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    wget \
    unzip \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-gpu.txt .
RUN pip install --no-cache-dir -r requirements-gpu.txt

# Source code only — data and checkpoints are mounted at runtime
COPY src/       ./src/
COPY scripts/   ./scripts/
COPY configs/   ./configs/

ENV PYTHONPATH=/workspace

CMD ["python", "scripts/train.py", "--config", "configs/base.yaml"]
