---
id: SEED-008
status: dormant
planted: 2026-05-22
planted_during: v2.0 / Phase 03 (corpus-inference) executing
trigger_when: Phase 3 (Corpus & Inference) generation latency becomes a felt constraint; or real-time call→response interaction inside Ableton becomes a goal; or Phase 4 evaluation throughput is bottlenecked by inference time
scope: Small
---

# SEED-008: Inference optimization pass — torch.compile, CoreML / Apple Neural Engine, INT8 quantization

## Why This Matters

Apollo's model is small and deliberately runs locally on Apple Silicon, but the inference path in `generate.py` (and the held-out sampling loop in Phase 4's diagnostic / evaluation tools) currently uses vanilla eager-mode PyTorch on MPS. There are three near-free wins from the ML-compiler world that map cleanly onto Apollo's tiny model:

| Technique | What it does | Effort | When to reach for it |
|---|---|---|---|
| `torch.compile(model)` | PyTorch's built-in graph compiler — operator fusion, kernel scheduling, reduced launch overhead | One line | Phase 3 once generate.py works; Phase 4 to speed up multi-temperature held-out sampling |
| CoreML export via `coremltools` | Lowers the trained model to Apple's Neural Engine (ANE), idle during Ableton sessions | A few hours, mostly model surgery for unsupported ops | Real-time call→response is a goal (e.g. Max-for-Live device, AU plugin path) |
| INT8 post-training quantization | Halves memory, often speeds up inference on supported ops | A few hours, plus held-out quality re-eval | When memory or latency is the felt constraint — likely not until the model grows |

These are deployment / runtime optimizations, not architecture changes. They preserve the trained checkpoint.

## When to Surface

**Trigger A — Phase 3 latency complaint.** When `generate.py` is in active use and a response takes long enough that the user notices, surface `torch.compile` first. One line, measure delta, ship.

**Trigger B — Phase 4 diagnostic throughput.** SEED-007's Tier 1 metrics require sampling N responses across K temperatures for every held-out call, every iteration. That's N×K×|held-out| forward passes per iteration. If diagnostic runtime becomes annoying, this seed's optimizations apply directly to the sampling loop, not just user-facing generation.

**Trigger C — Real-time Ableton integration becomes a goal.** Any path that puts Apollo *inside* Ableton (Max-for-Live device, AU plugin, OSC bridge) needs sub-100ms inference. That's when CoreML / ANE stops being optional. This is post-v1 — probably v2.1 or v3.

## Scope Estimate

**Small** — these are library-level integrations, not custom kernel work. The trap to avoid is treating this seed as a license to go deep on MLIR / TVM / custom CUDA — Apollo's model is too small for that to pay off and runs on hardware (MPS / ANE) that Apple already supports natively. Stay at the `torch.compile` / `coremltools` / `torch.quantization` level.

## Three Tiers (in order of expected ROI for Apollo)

### Tier 1 — `torch.compile` on the inference path (free win)

```python
# in generate.py and any held-out sampling loop
model = torch.compile(model)
```

Expected speedup on Apollo's transformer: 10–30% on MPS, possibly more on the mel-encoder CNN. Cost: first call pays compile time (~seconds). Worth measuring before and after with a fixed-seed sample.

Risk: MPS backend support for `torch.compile` is newer than CUDA. Verify it works on the actual model before declaring done — fall back to eager if any op is unsupported.

### Tier 2 — INT8 post-training quantization

Apply `torch.quantization` (or `torch.ao.quantization`) to the trained checkpoint. Re-run the held-out rubric eval — quantization-induced quality drop on a generative model is real and must be measured, not assumed. If the drop is meaningful, fall back to FP16 instead of INT8.

Cost: ~half a day, dominated by re-evaluation, not the quantization itself.

### Tier 3 — CoreML export to Apple Neural Engine

Convert the PyTorch model with `coremltools.convert(...)` to a `.mlpackage`. The ANE is dedicated silicon that's idle during a typical Ableton session — running inference there frees up CPU/GPU for audio processing.

Cost: real. Custom ops in the mel encoder or the sampling loop may not convert cleanly, requiring either rewrites or partial CoreML (encoder on ANE, decoder still on MPS). Realistic budget: 1–2 days of plumbing, plus held-out re-eval.

**Don't do Tier 3 until there's a concrete real-time goal.** Without an Ableton-side integration to plug into, the speedup is academic.

## Conceptual Background (for future-me)

The job posting that planted this seed describes the wider ML-compiler stack — MLIR, LLVM, TVM, Glow, custom CUDA — for deploying billion-parameter models on heterogeneous accelerators. **That stack is overkill for Apollo.** What's relevant is the *concept* — that ML inference can be optimized by graph rewrites (fusion), memory layout, and hardware-specific lowering — and that PyTorch's own compiler and Apple's CoreML already implement those passes for Apollo's case.

If Apollo ever ships as a product running on user hardware that *isn't* Apple Silicon (web demo, Linux, embedded), the relevance grows. Until then, this is a library-integration seed, not a compiler-engineering seed.

## How This Composes With Existing Seeds

- **SEED-007 (training sufficiency & diversity metrics):** Tier 1 diagnostics in SEED-007 require many forward passes per iteration. `torch.compile` on the sampling loop is the lowest-effort multiplier on diagnostic throughput.
- **SEED-001 (FM patch generation head):** When a patch-generation head is added, it's a new sub-graph. Re-run `torch.compile` after the architecture change.
- **SEED-004 (bidirectional chaining):** Multi-turn generation amplifies per-turn latency. Latency-sensitivity grows linearly with chain depth — making this seed's relevance grow alongside SEED-004.

## Breadcrumbs

- [apollo/scripts/generate.py](apollo/scripts/generate.py) — primary inference entry point; first place to wrap with `torch.compile`
- [apollo/scripts/train.py](apollo/scripts/train.py) — `torch.compile` can also speed up training; lower priority than inference
- [apollo/scripts/train_smoke.py](apollo/scripts/train_smoke.py) — smoke train is short; speedup here is nice-to-have, not load-bearing
- `.planning/phases/04-evaluation-loop/` — Phase 4's held-out sampling loop is the second target after `generate.py`
- `.planning/seeds/SEED-007-training-sufficiency-diversity-metrics.md` — diagnostic throughput tie-in

## Notes

Source: ChatGPT explainer about The Bot Company's ML compiler engineer role (2026-05-22 conversation). The user asked whether ML compiler concepts apply to Apollo. The honest answer was *tangentially* — Apollo's optimization story is library-level (`torch.compile`, CoreML, quantization), not compiler-engineering-level (MLIR / TVM / custom kernels). This seed captures the library-level wins to be picked up when latency becomes a real constraint, and explicitly warns future-me against scope creep into the full ML-compiler stack.
