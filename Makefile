.PHONY: test clean-fixtures clean-fixtures-dry sync

# Run the full local test suite (fixtures are generated on the fly via tmp_path).
test:
	python -m pytest -q

# Sync the Graphite stack after a PR merges on GitHub.
#
# Closes the "after-merge habit" gap: the restack-only git hooks fire on LOCAL
# merge/pull/rebase, but a GitHub PR merge fires nothing on your machine. Run this
# once after merging a PR to: fast-forward main, delete branches whose PRs merged,
# and retarget/rebase descendants.
#
# Intentionally INTERACTIVE (no --force): gt prompts before deleting any branch or
# force-pushing, so destructive cleanup is always surfaced, never silent.
sync:
	gt sync

# Wipe regenerable working artifacts before authoring/retraining on a real corpus:
# mock pairs, rendered wavs, eval score/run logs, render manifests, checkpoints.
#
# Uses `git clean -X`, which removes ONLY gitignored files and NEVER tracked ones,
# so the wipe list is always derived from .gitignore — tracked files like
# CORPUS-CONVENTIONS.md, rubric.md, delta.ipynb and the .gitkeep stubs are preserved
# automatically and this target can't drift out of sync.
clean-fixtures:
	git clean -fdX data/ models/ eval/

# Preview exactly what clean-fixtures would delete, without removing anything.
clean-fixtures-dry:
	git clean -ndX data/ models/ eval/
