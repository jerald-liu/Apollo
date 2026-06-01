# Apollo

Generative call-and-response for Ableton Operator (FM synth). You play a short MIDI phrase routed through an Operator preset; Apollo emits a complementary MIDI response in your authored style.

The training corpus is hand-authored in Ableton: paired MIDI tracks (call + response), both running Operator. The model conditions on the rendered audio of the call so it has timbre context, then generates MIDI for the response side only.

This is v2.0. The prior piano/MAESTRO codebase lives on the `deprecated` branch as historical reference only — it is *not* a model lineage. Apollo v1 trains from scratch.

---

## How it works

```mermaid
flowchart LR
    subgraph Author["1. Author (Ableton, by hand)"]
        A1[Record call MIDI<br/>0.5–1.5s, 2–6 notes]
        A2[Record response MIDI]
        A3[Bounce call to audio<br/>through Operator preset]
        A1 --> A3
        A1 --> P[data/pairs/NNN/<br/>call.mid · call.wav · response.mid]
        A2 --> P
        A3 --> P
    end

    subgraph Train["2. Train (local, MPS)"]
        P --> ING[ingest_corpus.py<br/>tokenize MIDI + extract mel]
        ING --> DS[ApolloDataset<br/>BOS · call · SEP · response · EOS]
        DS --> MDL[ApolloModel ~1.1M params<br/>MelEncoder CNN → prefix<br/>Transformer decoder]
        MDL --> CKPT[(checkpoint.pt)]
    end

    subgraph Infer["3. Generate (local, MPS)"]
        IN[New call.mid + call.wav] --> GEN[generate.py<br/>autoregressive sampling<br/>--temperature --top-k --n]
        CKPT --> GEN
        GEN --> OUT[response_NNN.mid]
        OUT --> AB[Play in Ableton<br/>through any preset]
    end

    style P fill:#fef3c7,stroke:#d97706
    style CKPT fill:#dbeafe,stroke:#2563eb
    style OUT fill:#dcfce7,stroke:#16a34a
```

**Three flows on one machine.** Everything runs on Apple Silicon (MPS) — no cloud, no GPU rental. The model is small (~1.1M params) by design.

**Why mel-condition on the call audio?** The Operator preset varies pair-to-pair. The model needs to "hear" the timbre of the prompt to know what a fitting response sounds like — a percussive bass call should not get the same response as a soft pad with the same notes.

**Why response-only loss?** Apollo is judged on what it generates, not on how well it reconstructs the prompt. Loss is masked to tokens after the `SEP` boundary.

---

## Quick start

```bash
python -m venv venv && source venv/bin/activate
pip install -e ".[dev]"

# Validate a corpus before training
python -m apollo.scripts.ingest_corpus data/pairs/

# Train on the real corpus (after ≥30 pairs are authored)
python -m apollo.scripts.train data/pairs/ \
  --epochs 300 --lr 1e-3 --batch-size 4 --iteration 1

# Generate a response
python -m apollo.scripts.generate \
  models/apollo_iter1_best.pt \
  data/pairs/001/call.mid data/pairs/001/call.wav \
  --n 4 --temperature 0.8 --top-k 10
```

`generate.py` writes `response_001.mid`, `response_002.mid`, … alongside the input call.

See [`data/pairs/CORPUS-CONVENTIONS.md`](data/pairs/CORPUS-CONVENTIONS.md) for authoring rules (120 BPM, preset variety, gesture length, file naming, ≥30 minimum).

### The evaluation loop (Phase 4)

After a training run, score the held-out pairs and check the ship gate:

```bash
# 1. Register the run + write the M4L render manifest (compute run_id, log to runs.jsonl)
python -m apollo.scripts.eval_render models/apollo_iter1_best.pt --iteration --iteration-label "iter 1"

# 2. Blind-grade the held-out responses in the local browser UI (127.0.0.1 only)
python -m apollo.scripts.eval_grade data/pairs/ --run-id <run_id>

# 3. Ship-gate decision: have two consecutive iterations both improved held-out score? (EVAL-05)
python -m apollo.scripts.eval_ship_check
```

Scores append to `eval/scores.jsonl`; the rubric lives in [`eval/rubric.md`](eval/rubric.md); `eval/delta.ipynb` charts per-iteration deltas. Before authoring or retraining on a fresh corpus, wipe regenerable artifacts (mock pairs, rendered wavs, score/run logs, manifests, checkpoints) without touching tracked files:

```bash
make clean-fixtures-dry   # preview what would be removed
make clean-fixtures       # remove gitignored working artifacts only
make test                 # full pytest suite
```

---

## Project status

| Phase | Scope | Status |
|---|---|---|
| 1 | Tokenizer & ingest pipeline | ✓ Complete |
| 2 | MelEncoder + ApolloModel + training | ✓ Complete |
| 3 | Corpus conventions, `generate.py`, `train.py` | ✓ Code complete; ≥30 pairs pending |
| 4 | Evaluation loop & ship gate | ✓ Code complete; corpus iterations pending |

**All four phases are code-complete (166 tests passing).** What remains is not code — it's the human-in-the-loop work the loop is built around: author ≥30 pairs in Ableton, run the first real training, grade the held-out responses, and iterate. v1 ships only when two consecutive active-learning iterations both improve held-out rubric scores. The loop itself — author → train → listen → identify gaps → author more — is the product, not any single checkpoint.

Authoritative planning lives in [`.planning/`](.planning/) — see [PROJECT.md](.planning/PROJECT.md), [ROADMAP.md](.planning/ROADMAP.md), [REQUIREMENTS.md](.planning/REQUIREMENTS.md).

---

## Repo layout

```
apollo/
  ingest/          # MIDI tokenizer, mel extractor, pair discovery, hash split
  model/           # MelEncoder (CNN), ApolloModel (transformer + mel prefix), training loop
  eval/            # run_id, runs/scores logs, ship-gate decision, render manifest
  eval/web/        # local Flask grading UI (127.0.0.1) — blind, resumable scoring
  scripts/         # ingest_corpus.py, train.py, generate.py, eval_render/grade/ship_check.py
  tokenizer/       # vocab + token helpers
data/pairs/        # authored pairs live here (gitignored by default)
eval/              # rubric.md, delta.ipynb, scores/runs logs (logs gitignored)
tests/             # pytest suite (run with `pytest` or `make test`)
.planning/         # project context, phase plans, requirements, sketches
.github/workflows/ # tests.yml (CI matrix)
```

### Contributing with stacked PRs

Stacks are maintained locally with Graphite (`gt`). Merge stacks to `main` — don't merge a PR into another feature branch expecting it to cascade (that's the squash-merge trap where a stacked child keeps stale commits and shows a bogus conflicting diff). After a base PR merges, run `gt sync` to retarget and rebase descendants.

Enable the restack-only git hooks once per clone:

```bash
git config core.hooksPath .githooks
```

These run `gt restack` after a merge/pull/rebase so your stack stays ordered. They **never** delete branches or force-push — for that, run `gt sync` explicitly.

---

## Design constraints (locked for v1)

- **Train from scratch.** Piano priors actively conflict with FM material.
- **Monophonic, tiny gestures.** 0.5–1.5s, 2–6 notes per side, quantized to a 120 BPM grid.
- **Just-notes vocab.** Pitch / velocity / time-shift / duration only. The vocab reserves room for pitch bend / mod wheel / CC tokens so future extensions don't invalidate existing checkpoints.
- **Mel-condition the call.** `call.wav` is a manual Ableton bounce committed alongside the MIDI.
- **Local-only.** No Modal, no cloud, no GPU rental for v1.

A known v1 limitation: Operator patches can produce perceived rhythm via LFOs/envelopes that aren't in the MIDI. Apollo "hears" that texture via the mel encoder but can only respond with notes, not synthesis parameters. Calls leaning heavily on LFO rhythm will get rhythmically "straight" responses. Deferred to a later milestone.
