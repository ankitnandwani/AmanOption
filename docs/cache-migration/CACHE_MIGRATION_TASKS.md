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

- [x] **Task 5 — Resumable migration utility**
  - Upload local cache files while preserving current key layout.
    - The key layout was wrong in the first implementation (`2025-04-04.pkl` instead of
      `historical_cache/2025-04-04.pkl`); migrated objects would have been unreachable by the
      application. Layout is now defined once in `services/cache_keys.py` and shared by the
      service layer and the tool, with a test asserting the two agree.
  - Support resume/retry and dry-run/listing.
    - `--list`, `--dry-run`, `--upload`, `--verify`; per-file state file written after every
      file; skip-on-existing; `--force`; exponential-backoff retries; non-zero exit on failure.
  - Verify object count, bytes, and checksums where feasible.
    - `--verify` compares object count, total bytes, per-object size and MD5 checksums.
      Checksums are stored as R2 object metadata at upload time; multipart ETags are reported
      as unverifiable rather than as mismatches.
  - Never delete originals.
    - The tool contains no delete/unlink/remove call; local files are only read. Asserted by
      unit tests both by source inspection and by comparing file content after a full upload.
  - The live upload run was deferred to Task 6.

- [x] **Task 6 — Test and compare**
  - Run the live migration against the target bucket (`--list` → `--dry-run` → `--upload` → `--verify`).
  - Test a known R2 hit and a known R2 miss.
  - Verify Upstox is not called on hits.
  - Verify a miss fetches and persists a reusable object.
  - Compare representative backtest results with the pre-migration baseline.
  - 2026-11-07: Uploaded 1,013 files totaling 3,340,758,071 bytes to `aman-options`.
    Verification matched every size and checksum, with zero extra objects. All 52 targeted
    offline tests passed.
  - Verification covered the uploaded snapshot. The local cache grew after the inventory
    during a separate backtest. See the handoff for the delta to reconcile before deployment.
  - Two two-day backtests matched the local baseline exactly. Each trading day took one
    R2 GET and zero Upstox historical-candle calls. An isolated miss fetched 385 candles
    from Upstox, persisted them to R2, and served them to a fresh local cache.

- [x] **Task 7 — Render deployment**
  - Configure R2 credentials and settings in Render environment variables.
    - Use the account-level `R2_ENDPOINT`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`,
      `R2_BUCKET_NAME=aman-options`, and `AWS_DEFAULT_REGION=auto`.
    - Also set `MAX_CACHE_SIZE_MB` explicitly (the deployed service already defaults to
      500 MB via `RENDER=true`, but set it so the bound does not depend on detection).
  - Verify logs do not leak secrets.
  - Validate cache hit/miss and multi-day behavior on the deployed service.
  - 2026-11-07: Local startup smoke test and all 52 targeted tests passed. The
    authenticated dashboard confirmed the `nicegui` branch and the start command.
    The isolated runtime revision passed 30 focused tests. Render environment
    configuration, deployment, logs, and live backtests remain pending.
  - 2026-11-08: Reconciled 16 new cache objects and five updates in R2. Full
    verification matched 1,029 files, 3,441,218,611 bytes, and all 1,029 checksums.
    The 52 targeted tests passed again. Render has six saved settings and still needs
    `R2_ACCESS_KEY_ID`. The rebuilt deployment candidate passed 30 focused tests.
  - 2026-11-09: Confirmed all seven Render environment keys. Publishing `b252ccc`
    requires GitHub write authentication. Deployment and live validation are pending.
  - Published `898e082` from the three tested files. Render went live on that
    revision after correcting the endpoint to the account URL and redeploying.
    Startup confirmed the 500 MB limit.
  - 2026-11-11: The live November 2–3 run matched the ₹2,772.25 baseline.
    The October 8 run populated all 34 missing contracts in R2 and preserved
    all 182 original entries. No credential patterns appeared in the visible
    startup and runtime log excerpts. All 52 targeted tests passed.

- [x] **Task 8 — Cutover and cleanup decision**
  - Confirm the new path is stable.
  - Keep original local files until explicit owner approval to remove them.
  - Decide separately what to do with `backtest_results/`; do not migrate it blindly.
  - 2026-11-12: The deployed app returned HTTP 200. The live R2 audit found a
    canonical object for each of the 1,029 local files. The only size difference
    was the October 8 object enriched during Task 7. All 52 targeted tests passed.
  - Retain the local originals and staged recovery data. Keep backtest history
    on the current filesystem. Two redundant R2 objects outside the canonical
    prefix are candidates for removal with owner approval.

## Current task
All migration tasks are complete. The Task 8 decision is ready for owner review.

## Out-of-band fix (2026-10-26)
A global 500 MB cache cap deleted the owner's 2024 data from the local cache while downloading 2025
data. The cap exists only to protect Render's small ephemeral disk, so it is now applied there only
(unlimited elsewhere, `0`/negative means unlimited). Covered by
`tests/test_cache_eviction_policy.py`.

## Rule
Complete one task at a time. Before each task, state intended changes and acceptance criteria; after it, report actual changed files and test evidence, then wait for approval.
