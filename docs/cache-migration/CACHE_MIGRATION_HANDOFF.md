# Cache Migration Handoff

## Project
AmanOptions — https://github.com/ankitnandwani/AmanOption

## Current state
Context and migration-planning documents have been prepared from owner-provided information and prior discussions. They have not been validated against a fresh checkout of the repository.

## Current task
Task 1 — Repository reconnaissance and plan validation.

## Next agent instructions
1. Read `AGENTS.md`, `docs/PROJECT_CONTEXT.md`, `docs/ARCHITECTURE.md`, `docs/DATA_AND_CACHE.md`, and all documents in `docs/cache-migration/`.
2. Check `git status` and preserve uncommitted changes.
3. Inspect only relevant cache, Upstox, backtest, dependency, deployment, and test files.
4. Identify actual names, paths, schemas, and tests; update the context documents with evidence from the code.
5. Do not change application code yet. Report findings and wait for approval.

## Changed files
- This context-document bundle is a proposed documentation package. No application source code was changed by preparing it.

## Tests
- Not run. Documentation-only draft; not yet installed into the repository.

## Known limitations
- Public web access did not reliably retrieve the specified repository during preparation, so repository-specific paths and implementation details are intentionally marked as unverified.
- `historical_cache/` and `backtest_results/` details are based on owner-provided context; contents of `backtest_results/` remain unknown.
