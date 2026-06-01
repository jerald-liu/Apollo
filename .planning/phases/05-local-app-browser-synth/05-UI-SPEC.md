---
phase: 5
slug: local-app-browser-synth
status: approved
shadcn_initialized: false
preset: none
created: 2026-06-01
---

# Phase 5 — UI Design Contract

> Visual and interaction contract for the Apollo local demo app. Authored from locked user decisions (no CONTEXT.md); verified by gsd-ui-checker.

## Locked Decisions (source of truth)

- **Purpose:** A purely **local**, public-demonstration front-end. Shows anyone — Ableton or not — how Apollo trains locally and generates responses. Local-only ethos: *data never leaves the machine*. Built in parallel with corpus tuning; depends only on shipped code (Phase 2 model + Phase 3 `train.py`/`generate.py`).
- **Aesthetic:** Playful / educational — bold color, big type, teaching annotations & tooltips.
- **Stack:** Vanilla JS + Web Audio API. No build step, minimal deps. Reuses the existing Flask eval UI conventions (`apollo/eval/web/`). The Operator-style FM synth is built directly on Web Audio (`OscillatorNode`×4 + `GainNode` ADSR across Operator's algorithm set; Tone.js `FMSynth` is 2-op only → scaffold at best).
- **Layout:** Dashboard + drill-in. Overview surfaces system state at a glance; each task has a drill-in view.
- **Emphasis:** All three equal — (a) call→response generation, (b) local-training visibility, (c) corpus building. The dashboard gives each first-class presence.

---

## Design System

| Property | Value |
|----------|-------|
| Tool | none (hand-rolled vanilla CSS, extends `apollo/eval/web/static/style.css`) |
| Preset | not applicable |
| Component library | none |
| Icon library | inline SVG + unicode glyphs (matches eval UI `.glyph` convention) |
| Font | system sans (`--font-body`) for UI; `--font-mono` for data/code/annotations |

Rationale: a no-build vanilla stack keeps the demo trivially launchable (`python -m apollo.app`) and consistent with the existing eval web surface. CSS custom properties carry the design tokens below.

---

## Spacing Scale

Declared values (multiples of 4) — extends the eval UI's existing `--xs..--xl`:

| Token | Value | Usage |
|-------|-------|-------|
| xs | 4px | Icon gaps, inline padding, glyph spacing |
| sm | 8px | Compact element spacing, control padding |
| md | 16px | Default element spacing, card padding |
| lg | 24px | Section padding, card gaps |
| xl | 32px | Layout gaps between dashboard tiles |
| 2xl | 48px | Major section breaks, drill-in header offset |
| 3xl | 64px | Page-level top/bottom rhythm, hero band |

Exceptions: synth keyboard key width (`44px` touch target) and score/transport buttons (`40px`, inherited from eval UI) are fixed control sizes, not layout spacing.

---

## Typography

Playful/educational → larger display + heading sizes than the eval UI, same families. Constrained to 4 sizes and 2 weights; mono family + muted color (not extra sizes/weights) carry the remaining differentiation.

| Role | Size | Weight | Line Height |
|------|------|--------|-------------|
| Body | 16px | 400 | 1.5 |
| Label | 14px | 400 | 1.4 |
| Heading | 24px | 700 | 1.3 |
| Display | 40px | 700 | 1.15 |

Annotations/teaching captions use `--font-mono` at the Label size (14px) / 1.4 / `--muted` — the mono family + muted color distinguish them, no separate size or weight. Numeric stats (pair count, loss, epoch) use `--font-mono` at Body/Display size for tabular legibility.

---

## Color

60 / 30 / 10 split. Bold accent for the "playful" register; light base keeps the teaching content readable for a general audience.

| Role | Value | Usage |
|------|-------|-------|
| Dominant (60%) | `#FAFAFA` | App background, page canvas |
| Secondary (30%) | `#F0F0F0` | Dashboard tiles, cards, drill-in surfaces, synth panel |
| Accent (10%) | `#6D28D9` | Primary CTAs, active synth keys, progress fill, selected states, "data stays local" badge |
| Destructive | `#CC3333` | Delete pair, discard response, stop-training confirmations only |

Accent reserved for: primary CTA buttons (Generate, Add pair, Train), the corpus-progress bar fill, the active/selected state of synth keys and segmented controls, and the local-only trust badge. **Never** applied to all interactive elements, body links, or card borders.

Supporting (not accent, documented to prevent accent creep):
- Success/ready: `#15803D` — used only for "training complete" / "ready to generate" status dots.
- Annotation surface: `#F0F0F0` (`--surface`) background for teaching callouts; text in `--muted` `#666666`.

Dominant/secondary/`--muted`/`--destructive` reuse the eval UI's existing tokens verbatim for cross-surface consistency.

---

## Copywriting Contract

Voice: encouraging, plain-language, teaches as it goes. Reinforces local-only at trust moments.

| Element | Copy |
|---------|------|
| Primary CTA (generate) | "Generate response" |
| Primary CTA (corpus) | "Add pair" |
| Primary CTA (train) | "Train model" (dashboard tile may abbreviate to "Train now" where tile context supplies the noun) |
| Auto-retrain toggle label | "Re-train automatically after each new pair" |
| Local-only trust badge | "Runs on your machine — nothing is uploaded" |
| Empty state heading (corpus) | "No pairs yet" |
| Empty state body (corpus) | "Drag in a call + response, or play them on the synth. Apollo needs about 30 pairs to start learning your style — add your first one to begin." |
| Empty state heading (responses) | "No responses generated yet" |
| Empty state body (responses) | "Upload or play a call, then hit Generate response to hear what Apollo plays back." |
| Corpus progress label | "{n} of 30 pairs — keep going" (after 30: "{n} pairs — more is better") |
| Training in progress | "Training locally… epoch {e}/{total}" |
| Training complete | "Training complete — ready to generate" |
| Error state (invalid pair) | "This pair doesn't match the format: {reason}. See the authoring guide and try again." |
| Error state (no checkpoint) | "No trained model yet. Add a few pairs and train first, then generate." |
| Destructive confirmation (pair) | "Delete pair: This removes it from your corpus. It won't affect already-trained models. Delete?" |
| Destructive confirmation (stop training) | "Stop training: Progress for this run will be lost. Stop?" |
| Response storage setting | "Save generated responses to: {folder}" |

---

## Layout Contract (Dashboard + drill-in)

**Visual hierarchy / focal point:** within the equal-weight-tile constraint, the eye lands first on the **corpus progress count** rendered at Display size (40px) inside the Corpus tile — it is the page's primary anchor and the demo's running scoreboard. Secondary anchor is the **training status dot** (color-coded: untrained/training/ready). The header trust badge is persistent but quiet (Label size, muted). Equal *weight* means each tile gets equal area and a Display-size headline number/CTA; it does not mean zero hierarchy.

**Dashboard (home)** — three equal-weight tiles + a global local-only trust badge in the header:
1. **Corpus** tile — pair count vs. 30 target with progress bar, "Add pair" CTA, drag-drop zone.
2. **Training** tile — model status dot (untrained / training / ready), "Train now" CTA, auto-retrain toggle, last-run epoch/loss.
3. **Generate** tile — "Generate response" CTA, recent responses list (auditionable inline).

**Drill-in views** (one per tile, back-nav to dashboard):
- Corpus → pair list, per-pair audition (call/response via synth), validation errors inline, delete.
- Training → live progress (epoch/loss readout, progress bar), run history, response-storage folder setting.
- Generate → call input (upload MIDI or play on synth keyboard), synth patch controls (4 operators, algorithm selector, ADSR), generate, audition response.

The in-browser synth is a shared component surfaced in both Corpus (author/audition) and Generate (play call, audition response).

---

## Registry Safety

| Registry | Blocks Used | Safety Gate |
|----------|-------------|-------------|
| none (vanilla CSS/JS, no component registry) | — | not applicable |

No shadcn or third-party component registry is used. The only runtime dependency consideration is whether to pull Tone.js as a synth scaffold; the locked decision is to build on raw Web Audio, so no registry/CDN component-trust gate applies. Any future Tone.js inclusion would be a vendored, pinned dependency reviewed at plan time.

---

## Checker Sign-Off

- [x] Dimension 1 Copywriting: PASS
- [x] Dimension 2 Visuals: PASS
- [x] Dimension 3 Color: PASS
- [x] Dimension 4 Typography: PASS
- [x] Dimension 5 Spacing: PASS
- [x] Dimension 6 Registry Safety: PASS

**Approval:** approved 2026-06-01
