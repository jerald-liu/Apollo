---
phase: 4
slug: 04-evaluation-loop
status: verified
threats_open: 0
asvs_level: 1
created: 2026-05-23
---

# Phase 4 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Flask dev server | Grading UI bound to 127.0.0.1 only | MIDI metadata, scores (non-sensitive, single-user localhost) |
| URL route params | `nnn` pair ID in Flask routes | User-controlled string → filesystem path construction |
| JSONL data files | eval/scores.jsonl, eval/runs.jsonl | Append-only local files, no remote access |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-4-01 | Tampering | Flask routes | mitigate | `nnn` validated against `enumerate_heldout` set membership BEFORE any `Path` construction. Tests: `test_pair_view_path_traversal_returns_404`, `test_audio_path_traversal_blocked` | closed |
| T-4-02 | Info Disclosure | Network binding | mitigate | `eval_grade.py` hardcodes `host="127.0.0.1"` — non-negotiable per RESEARCH §Anti-Patterns. No `--host` flag exposed. | closed |
| T-4-03 | Spoofing | Grading integrity | accept | Single-user localhost tool — user is both grader and model trainer. Honour mode applies. No auth needed. | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-4-01 | T-4-03 | Single-user local tool; user grades their own model's output. Adding auth would add complexity with no security benefit. | gsd-security-audit | 2026-05-23 |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-05-23 | 3 | 3 | 0 | gsd-secure-phase |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-05-23
