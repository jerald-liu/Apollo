.PHONY: smoke preprocess train build modal-preprocess modal-train pull-checkpoints help

VENV        := venv/bin
PYTHON      := $(VENV)/python
MODAL       := $(VENV)/modal
CONFIG      ?= configs/base.yaml
RESUME      ?=
SPECTRAL    ?= false
IMAGE_TAG   ?= apollo:latest

help:
	@echo "Local:"
	@echo "  make smoke              Correctness check: 200 steps, tiny model, MPS/CPU"
	@echo "  make preprocess         MIDI-only preprocessing into data/processed/"
	@echo "  make train              Full training run locally (slow without GPU)"
	@echo ""
	@echo "Docker:"
	@echo "  make build              Build CUDA training image"
	@echo ""
	@echo "Modal (cloud GPU):"
	@echo "  make modal-preprocess   Download MAESTRO + preprocess onto apollo-data volume"
	@echo "  make modal-train        Train on A100 (~6-8h, ~\$$5-15)"
	@echo "  make pull-checkpoints   Download best checkpoint from Modal volume"
	@echo ""
	@echo "Overrides: make modal-train CONFIG=configs/large.yaml RESUME=checkpoint_latest.pt"

# ---------------------------------------------------------------------------
# Local
# ---------------------------------------------------------------------------

smoke:
	$(PYTHON) scripts/train.py --config configs/smoke.yaml

preprocess:
	$(PYTHON) scripts/preprocess.py \
		--midi-dir data/raw/maestro-v3.0.0 \
		--output-dir data/processed

train:
	$(PYTHON) scripts/train.py --config $(CONFIG) $(if $(RESUME),--resume $(RESUME),)

# ---------------------------------------------------------------------------
# Docker
# ---------------------------------------------------------------------------

build:
	docker build -t $(IMAGE_TAG) .

# ---------------------------------------------------------------------------
# Modal (requires: pip install modal && modal setup)
# ---------------------------------------------------------------------------

modal-preprocess:
	$(MODAL) run modal_train.py --action preprocess --spectral $(SPECTRAL)

modal-train:
	$(MODAL) run modal_train.py --action train --config $(CONFIG) $(if $(RESUME),--resume $(RESUME),)

pull-checkpoints:
	@mkdir -p models
	$(MODAL) volume get apollo-checkpoints checkpoint_best.pt   models/checkpoint_best.pt   2>/dev/null || true
	$(MODAL) volume get apollo-checkpoints checkpoint_latest.pt models/checkpoint_latest.pt 2>/dev/null || true
	@echo "Checkpoints pulled to models/"
