#!/usr/bin/env bash
# Shared helper: restack the Graphite stack after a git event that may have moved
# a branch's base (merge, pull, rebase). RESTACK ONLY — this never deletes a
# branch and never force-pushes. It reorders local branches so children sit on
# their updated parents.
#
# Safe by construction:
#   - no-op if Graphite (`gt`) isn't installed
#   - no-op if this repo isn't tracked by Graphite
#   - never fails the triggering git operation (always exits 0)
#
# To run a full sync (pull trunk + delete merged branches + force-push children),
# do that explicitly with `gt sync` — it is intentionally NOT automated here.

set +e  # never let a hook failure abort the git operation

command -v gt >/dev/null 2>&1 || exit 0

# Only act if Graphite is initialized for this repo.
gt repo init --help >/dev/null 2>&1 || true
if ! gt ls >/dev/null 2>&1; then
  exit 0
fi

echo "↻ gt restack (auto, restack-only — no delete, no force-push)"
gt restack >/dev/null 2>&1 || true
exit 0
