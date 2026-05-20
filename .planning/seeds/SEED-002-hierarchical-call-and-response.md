---
id: SEED-002
status: dormant
planted: 2026-05-19
planted_during: v2.0 / Phase 03 (corpus-inference)
trigger_when: After v1 ships (two consecutive held-out-score improvements confirmed)
scope: Large
---

# SEED-002: Hierarchical call-and-response for passage/songwriting scaffolding

## Why This Matters

The nested architecture solves two problems simultaneously:

**Structure:** Apollo v1 operates at the gesture level (A→B, ~1 second, 2–6 notes). By treating completed call/response pairs as atomic units, a second model can learn call-and-response at the *theme* level — T1→T2 where T1=(A→B) and T2=(A→C) or (A→B'). Repeating this nesting produces musical passages with internal coherence: development sections (B'), contrasting themes (C), returns (A again). This is the computational analog of classical form logic.

**Signal:** Theme-level pairs give the model stronger musical context than isolated gestures. A model that sees "this theme followed that theme" learns a higher-order grammar of musical conversation — not just note-to-note, but idea-to-idea.

Apollo v1's mel encoder + transformer can serve as the feature extractor that feeds this second-level model. The architecture nests naturally — no re-architecture from scratch.

## When to Surface

**Trigger:** After v1 ships — once two consecutive held-out-score improvements confirm the gesture-level active-learning loop works. That validation is the prerequisite: it proves the foundation is solid enough to build upward.

This seed should be presented during `/gsd-new-milestone` when:
- Phase 4 (Evaluation Loop) is complete and the ship gate was reached
- The milestone scope mentions songwriting, composition, structure, or passage-level generation
- The milestone scope mentions multi-level or hierarchical modeling

## Scope Estimate

**Large** — A full milestone. Requires:
- New corpus format: theme-level pairs where each "note" in the higher model is a gesture embedding from v1
- New authoring workflow: user authors sequences of gesture pairs that form a theme, then theme pairs that form a passage
- Second model: operates on v1 gesture embeddings as tokens; learns theme-level call-and-response
- Evaluation: listen-test rubric extended to theme-level coherence (does T2 answer T1?)

## Breadcrumbs

- `.planning/PROJECT.md` — Out of Scope: "Synthesis-level rhythmic response" (999.2); Key Decisions table; Core Value statement
- `.planning/ROADMAP.md` — Backlog 999.1 (FM patch generation head), Backlog 999.2 (synthesis-level rhythm); Phase 4 evaluation loop (prerequisite)
- `.planning/REQUIREMENTS.md` — EVAL-01..EVAL-05 (ship gate criteria that must be met before this surfaces)
- `apollo/model/model.py` — ApolloModel (transformer + mel prefix); the gesture-level model whose embeddings become the token vocabulary for the theme-level model
- `apollo/model/mel_encoder.py` — MelEncoder (109,184 params CNN); the feature extractor that would be reused or frozen at the theme level

## Notes

The B' vs C distinction (development vs contrast) maps directly to classical form logic and is musically precise. A theme-level model that learns when to develop (B') vs contrast (C) is essentially learning musical phrase structure — the foundation for verse/chorus/bridge type organization in electronic music.

The user's framing: "enough call/responses and themes that will be encapsulated in a passage" — a passage is the natural output unit of a v2 milestone. Eventually a third level could produce full compositional forms, but that's far future.
