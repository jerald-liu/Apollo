# Phase 1: Training - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-13
**Phase:** 01-training
**Areas discussed:** Run sequencing

---

## Run sequencing

| Option | Description | Selected |
|--------|-------------|----------|
| Parallel — launch both together | Done in ~12h. 2× spend rate. Risk of billing limit if headroom is limited. | ✓ |
| Sequential — v3 first, then v4 | Done in ~24h. Lower risk per run. Can confirm v3 stable before starting v4. | |

**User's choice:** Parallel — launch v3 and v4 simultaneously

**Notes:** User initially asked "why can't we just do v4?" — clarified that v3 validates mel conditioning against the v2 baseline, and both runs are needed per the milestone goal. User confirmed both runs as planned.

---

## Run scope (follow-up)

| Option | Description | Selected |
|--------|-------------|----------|
| Both runs — keep as planned | v3 validates mel conditioning vs v2. v4 is the inference model. | ✓ |
| v4 only — skip v3 | Simpler, faster, lower cost. Skip mel conditioning experiment for now. | |

**User's choice:** Both runs as planned

---

## Billing resolution

| Option | Description | Selected |
|--------|-------------|----------|
| Wait for automatic cycle reset | Check Modal dashboard for reset date, then launch. | |
| Increase the limit / upgrade plan | Contact Modal support or upgrade spending limit. | |
| Already resolved — ready to launch | Billing is sorted, ready to proceed. | ✓ |

**User's choice:** Already resolved — ready to launch immediately

---

## Claude's Discretion

- Monitoring approach (WandB vs Modal console logs)
- Early stopping / intervention criteria for diverging runs
- Checkpoint verification steps before Phase 2 handoff

## Deferred Ideas

None.
