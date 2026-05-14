.PHONY: smoke preprocess train build modal-preprocess modal-preprocess-mel modal-train pull-checkpoints install-m4l help

M4L_DIR     ?= $(HOME)/Music/Ableton/User Library/Presets/MIDI Effects/Max MIDI Effect/Apollo

VENV        := venv/bin
PYTHON      := $(VENV)/python
MODAL       := $(VENV)/modal
CONFIG      ?= configs/base.yaml
RESUME      ?=
SPECTRAL    ?= false
MEL         ?= false
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
	@echo ""
	@echo "Max for Live:"
	@echo "  make install-m4l        Install device to Ableton User Library (needs Live Suite)"
	@echo "  Override: make install-m4l M4L_DIR=/path/to/custom/dir"

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
	$(MODAL) run modal_train.py --action preprocess $(if $(filter true,$(SPECTRAL)),--spectral,) $(if $(filter true,$(MEL)),--mel,)

modal-preprocess-mel:
	$(MODAL) run modal_train.py --action preprocess --mel

modal-train:
	$(MODAL) run modal_train.py --action train --config $(CONFIG) $(if $(RESUME),--resume $(RESUME),)

pull-checkpoints:
	@mkdir -p models
	$(MODAL) volume get apollo-checkpoints apollo_v3_mel/checkpoint_best.pt    models/checkpoint_v3_best.pt    2>/dev/null || true
	$(MODAL) volume get apollo-checkpoints apollo_v3_mel/checkpoint_latest.pt  models/checkpoint_v3_latest.pt  2>/dev/null || true
	$(MODAL) volume get apollo-checkpoints apollo_v4_streaming/checkpoint_best.pt    models/checkpoint_v4_best.pt    2>/dev/null || true
	$(MODAL) volume get apollo-checkpoints apollo_v4_streaming/checkpoint_latest.pt  models/checkpoint_v4_latest.pt  2>/dev/null || true
	@echo "Checkpoints pulled to models/"
	@ls -lh models/checkpoint_v*.pt 2>/dev/null || echo "Warning: no checkpoint_v*.pt files found"

# ---------------------------------------------------------------------------
# Max for Live device install
# Copies patcher + JS files to Ableton User Library.
# Requires Ableton Live Suite (or Live + M4L add-on).
# ---------------------------------------------------------------------------

install-m4l:
	@echo "Installing Apollo M4L device to:"
	@echo "  $(M4L_DIR)"
	@mkdir -p "$(M4L_DIR)"
	@cp m4l/patchers/apollo_engine.maxpat "$(M4L_DIR)/Apollo.maxpat"
	@cp m4l/code/apollo_bridge.js         "$(M4L_DIR)/"
	@cp m4l/code/apollo_status.js         "$(M4L_DIR)/"
	@cp m4l/code/apollo_activity.js       "$(M4L_DIR)/"
	@cp m4l/code/apollo_timbre_meters.js  "$(M4L_DIR)/"
	@echo "Done. Restart Ableton and find Apollo in:"
	@echo "  Browser → User Library → Presets → MIDI Effects → Max MIDI Effect → Apollo"
