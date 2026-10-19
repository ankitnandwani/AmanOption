# Cache Migration Tasks

Status key: `[ ]` not started · `[x]` completed · `[~]` in progress. Update only when there is evidence.

- [x] **Task 1 — Repository reconnaissance and plan validation**
  - Inspect only the relevant source/config/test paths.
  - Identified actual cache reads/writes, Upstox fetch, cache key, pickle schema, multi-day call path, and test commands.
  - Recorded findings in `docs/ARCHITECTURE.md` and `docs/DATA_AND_CACHE.md`.
  - No application code changes.

- [x] **Task 2 — R2 adapter**
  - Add minimal object existence/get/put operations using the project's dependency conventions.
  - Unit tests use mocks; no live credentials required.
  - Credentials supplied via environment variables; no secrets in code.

- [x] **Task 3 — Cache integration**
  - Add local-cache → R2 → existing Upstox fallback.
  - Preserve current cache interface and file compatibility.
  - Unit tests for local hit, R2 hit, full miss, and persistence.

- [x] **Task 4 — Multi-day efficiency and reliability**
  - Test that repeated access does not repeat downloads/deserialization unnecessarily.
  - Bound local cache usage.
  - Address concurrent same-key misses, partial downloads, retries/timeouts, and clear failure behavior.
  - Add limited concurrency/prefetch only if justified.

- [ ] **Task 5 — Resumable migration utility**
  - Upload local cache files while preserving current key layout.
  - Support resume/retry and dry-run/listing.
  - Verify object count, bytes, and checksums where feasible.
  - Never delete originals.

- [ ] **Task 6 — Test and compare**
  - Test a known R2 hit and a known R2 miss.
  - Verify Upstox is not called on hits.
  - Verify a miss fetches and persists a reusable object.
  - Compare representative backtest results with the pre-migration baseline.

- [ ] **Task 7 — Render deployment**
  - Configure R2 credentials and settings in Render environment variables.
  - Verify logs do not leak secrets.
  - Validate cache hit/miss and multi-day behavior on the deployed service.

- [ ] **Task 8 — Cutover and cleanup decision**
  - Confirm the new path is stable.
  - Keep original local files until explicit owner approval to remove them.
  - Decide separately what to do with `backtest_results/`; do not migrate it blindly.

## Current task
Task 5 — Resumable migration utility

## Rule
Complete one task at a time. Before each task, state intended changes and acceptance criteria; after it, report actual changed files and test evidence, then wait for approval.
