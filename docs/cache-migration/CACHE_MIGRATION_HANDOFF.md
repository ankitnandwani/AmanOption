# Cache Migration Handoff

## Project
AmanOptions — https://github.com/ankitnandwani/AmanOption

## Current state
The existing local cache has been uploaded and verified against live R2 in the `aman-options`
bucket. The application and migration tool share their key layout through
`services/cache_keys.py`.

The Task 5 code, cache-policy fix, tests, and Task 6 documentation are uncommitted.
`HEAD` is still `b51b339` ("task5"). Preserve this work and keep credential files and large
data files out of commits.

## Cache policy fix (2026-10-26)
A global 500 MB cache cap deleted the owner's 2024 data from the local cache on 2026-10-26, when
downloading 2025 data pushed the folder over the limit and the eviction helper removed the oldest
files. The cap exists only to protect Render's small ephemeral disk, so it is now applied there
only: `MAX_CACHE_SIZE_MB` (read once at import) is unlimited outside Render, 500 MB on Render
(detected via `RENDER=true`), `0` or negative means unlimited, and an explicit value is honoured.
Eviction also now orders by modification time, never removes the newest file, logs what it removed,
and is throttled to one directory scan every 5 seconds. Covered by
`tests/test_cache_eviction_policy.py` (11 tests).

## Current task
Task 8 — Cutover and cleanup decision is complete and ready for owner review.

### Task 7 preflight (2026-11-07)

- The owner signed in to the [AmanOption Render service](https://dashboard.render.com/web/srv-d99tuvks728c73dsjso0).
  The dashboard links to the `nicegui` branch of `ankitnandwani/AmanOption` and shows
  `b51b339` live. Build uses `pip install -r requirements.txt` and startup uses
  `python -m ui.ui`. The service Environment page showed no R2 keys.
- The candidate start command `python -m ui.ui` returned HTTP 200 and served the
  Options Trading Bot UI in an isolated local run. With `RENDER=true` and
  `MAX_CACHE_SIZE_MB=500`, it logged the expected limit and left the temporary cache
  empty. Render already uses this command.
- The same 52 targeted tests from Task 6 passed again in a temporary working
  directory with live credentials removed. The six known Task 4 failures were
  outside this run.
- GitHub reported `nicegui` at `b51b339` and `main` at `3b9024f`.
  Prepared local candidate `f090edd` on top of `b51b339` in the isolated checkout
  `/tmp/amanoptions-task7-source.ihRJgm`. It includes only `services/cache_keys.py`,
  `services/historical_service.py`, and `services/r2_service.py`. All 30 focused
  adapter, cache integration, and eviction tests passed against the candidate.
  The workspace index still contains `.env.local` and the staged cache/result files.
- The candidate is local. The deployment, runtime log review, and live validation
  remain pending.

### Task 7 cache reconciliation (2026-11-08)

- The settled local inventory contained 1,029 files. The live R2 comparison found
  16 additions and five updates. Each update retained every existing contract key
  and nonempty candle series. The uploads used conditional writes to protect against
  concurrent changes, and each of the 21 written objects passed size and checksum
  metadata checks.
- Full `--verify` passed for 1,029 objects and 3,441,218,611 bytes. All 1,029
  checksums matched. The report showed zero missing or extra keys, size mismatches,
  checksum mismatches, and unverifiable checksums.
- The 52 targeted tests passed again. GitHub still reports `nicegui` at `b51b339`.

### Task 7 Render settings check (2026-11-08)

- The owner saved six variables in Render. The dashboard confirmed the endpoint,
  secret access key, bucket, AWS region, cache limit, and Upstox token by name.
  `R2_ACCESS_KEY_ID` is the remaining missing key. Credential values were kept out
  of the check output.
- Recreated the isolated deployment candidate as `b252ccc` on top of `b51b339`
  because the previous temporary checkout was gone. The three runtime files passed
  all 30 focused tests again. The checkout is at `/tmp/amanoptions-task7-publish.4NAtGD`.
  GitHub's `nicegui` tip is still `b51b339`.

### Task 6 evidence (2026-11-07)
- With the R2 settings supplied, `--list` found zero objects under `historical_cache/`
  in `aman-options`. `--dry-run` planned 1,013 uploads and zero replacements. `--upload`
  transferred 1,013 objects and 3,340,758,071 bytes with zero failures.
- `--verify` matched object counts, total bytes, and per-object sizes. All 1,013 checksums
  matched, with zero missing or extra objects and zero unverifiable checksums.
- The working cache changed after the migration inventory during a separate local backtest.
  A later inventory found new files for 2026-07-20 through 2026-07-22 and a different
  size for 2026-07-19. The verification applies to the 1,013-file migration snapshot.
  Reconcile the delta after the local writer finishes and review any replacements
  before deployment.
- The shell had inherited an AWS region that R2 rejected. The migration process used
  `AWS_DEFAULT_REGION=auto` and the account-level HTTPS endpoint, with the bucket name
  passed separately. The source environment files were left in place.
- All 52 tests in `test_migrate_cache_to_r2`, `test_r2_service`, `test_historical_service`,
  and `test_cache_eviction_policy` passed from a temporary working directory with live R2
  and Upstox credentials removed from the test process. These cover offline upload and
  verification, cache hit and miss handling, persistence, and eviction. The six known
  Task 4 test-harness failures were outside this run.
- The saved backtest JSON files lack strategy configuration, so the comparison uses a
  fresh baseline from copies of the original pickles. Both runs use frozen Upstox contract
  metadata, the Nifty 50 underlying, one lot, target premium 35, 20% stop loss, and a 3,000
  max loss. The selected ranges are 2026-10-26 to 2026-10-27 and 2026-11-02 to 2026-11-03.
- The R2-backed run started with empty local and in-memory caches. It downloaded each
  day once, reproduced the source candle payloads, and made zero Upstox historical-candle
  calls. Daily P&L, range P&L, and win rate matched the local baseline:

  | Dates | Daily P&L | Range P&L | Win rate |
  |---|---:|---:|---:|
  | 2026-10-26 to 2026-10-27 | -4,182.75, -3,705.00 | -7,887.75 | 0% |
  | 2026-11-02 to 2026-11-03 | 770.25, 2,002.00 | 2,772.25 | 100% |

- A known miss on 2026-11-03 called live Upstox once, fetched 385 candles, and wrote the
  expected pickle to R2. Starting with a fresh local and in-memory cache returned the
  same candles from R2 with zero Upstox calls. The probe object remains at
  `cache-migration-validation/task6-20261107-01a1/2026-11-03.pkl`, outside the
  application and migration prefix.
- Task 6 changes are documentation only. Existing staged work and the source cache were
  preserved. Git showed a staged `.env.local` containing R2 credential fields during
  the run. Keep it out of commits.

### Task 7 publishing check (2026-11-09)

- The dashboard confirmed all seven environment variable names after a reload, including
  `R2_ACCESS_KEY_ID`. Values were omitted from the check output.
- GitHub still reports `nicegui` at `b51b339`. The fast-forward push of the tested
  `b252ccc` revision stopped because the shell has no GitHub HTTPS credentials.
  The SSH agent has no usable identity, and the GitHub tab shows Sign in.
- The owner signed in to GitHub in Firefox. Codex could not control the native
  Firefox window because computer-use permission was unavailable. GitHub sign-in
  in the Codex browser or an authenticated push remains the next step.

### Task 7 deployment (2026-11-09)

- The signed-in GitHub browser published the three runtime cache files to
  `nicegui` as `898e082`. The commit is a direct child of `b51b339` and Git
  reported no tree difference from the tested `b252ccc` revision. The published
  tree excludes credentials, cache files, and backtest outputs.
- The first Render backtest received `NoSuchKey` for a verified cache object.
  The saved endpoint included the bucket path. Removed that path and redeployed
  the same commit. Render confirmed the deployment was live and logged the 500 MB
  cache limit. One object created by the first attempt remains at
  `aman-options/historical_cache/2026-11-02.pkl`, outside the normal cache prefix.
- Corrected [Render deployment](https://dashboard.render.com/web/srv-d99tuvks728c73dsjso0/deploys/dep-dbov8nc9v7es738g4tbg).

### Task 7 live validation (2026-11-11)

- Render still showed `898e082` live with the 500 MB cache limit. A fresh
  November 2–3 backtest, `job_20261111_164142`, completed with daily P&L of
  ₹770.25 and ₹2,002.00 and total P&L of ₹2,772.25, matching Task 6.
  The reviewed logs showed no historical candle misses for this run.
  Both R2 objects still matched the original local bytes.
- All 52 targeted tests passed in an isolated working directory with live
  credentials removed. The six known Task 4 failures were outside this run.
- The October 8 replay, `job_20261111_175324`, completed with P&L of ₹555.75.
  Upstox metadata listed 216 contracts and the starting R2 object had 182.
  The final object contained all 216 entries, including 26 new entries with
  candles and eight new empty entries. All 182 original entries matched.
  This verifies that the deployed fallback persisted its data to R2.
- The visible startup and runtime log excerpts contained no credential patterns.
  The runtime view did not show the October 8 fallback lines, so the miss
  check uses the backtest result and the before-and-after R2 payload comparison.

### Task 8 cutover review (2026-11-12)

- The public Render URL returned HTTP 200 and served the Options Trading Bot UI.
  This availability check complements the completed Task 7 live backtests.
- The read-only R2 inventory found 1,029 canonical objects totaling
  3,442,156,706 bytes. The 1,029 local files totaled 3,441,218,611 bytes.
  The key sets matched. November 2 and 3 matched byte for byte. October 8 was
  the only size difference and its R2 object held 216 contracts, preserving all
  182 local entries. Checksums were sampled for this review. The last full
  snapshot verification was on November 8, before the live October 8 enrichment.
- The local backtest results directory had 64 JSON results and 93 status files,
  totaling 75,852 bytes. Keep the local files and treat hosted history as
  ephemeral. The history loader reads per-job results for display and the
  backtester uses historical candles as input. [Render Free filesystem behavior](https://render.com/docs/free#local-files-lost-on-redeploy)
- Two objects are outside the active prefix. The canonical dates contain all
  their contract keys and every nonempty candle series. Retain both until the
  owner approves removal of the exact keys.
  - `aman-options/historical_cache/2026-11-02.pkl` (2,390,915 bytes).
  - `cache-migration-validation/task6-20261107-01a1/2026-11-03.pkl` (41,008 bytes).
- All 52 targeted tests passed again in an isolated working directory. Task 8
  changed only documentation. The local originals and Git index were preserved.

## Next agent instructions
The migration tracker is complete. If the owner authorizes R2 cleanup, recheck
the two exact keys against their canonical objects immediately before removing
them. Treat local originals and staged recovery files as a separate decision.

## Changed files
- `migrate_cache_to_r2.py` — rewritten: `--list` / `--dry-run` / `--upload` / `--verify` modes,
  resumable per-file state file, retry with exponential backoff, MD5/SHA-256 checksums stored as
  R2 object metadata, verification of object count / bytes / sizes / checksums, and a guarantee
  that local files are never modified or deleted.
- `services/cache_keys.py` — **new**. Single source of truth for the cache key layout
  (`R2_KEY_PREFIX`, `cache_file_name()`, `r2_object_key()`), shared by the service layer and the
  migration tool so the two cannot drift apart.
- `services/r2_service.py` — added `put_file()` (managed streaming upload), `head_object()`,
  `list_objects()` (paginated), and an optional `metadata` argument on `put_object()`. The
  client now sets `request_checksum_calculation="when_required"` so botocore does not attach a
  CRC32 `ChecksumAlgorithm` that R2 does not reliably accept.
- `services/historical_service.py` — the R2 object key is now built from `services/cache_keys`.
  The generated key string is unchanged (`historical_cache/{day_key}.pkl`).
- `tests/test_migrate_cache_to_r2.py` — **new**. 22 tests for the migration utility.
- `tests/test_r2_service.py` — 4 new tests that check the adapter against the real botocore API
  contract using a stubbed S3 client; updated the client-construction assertion.
- `tests/test_historical_service.py` — safety fix: the cache directory is redirected to a
  temporary directory and eviction is disabled for the duration of the tests.
- `tests/test_cache_eviction_policy.py` — **new**; 11 tests pinning the eviction policy: local
  default is unlimited, `0`/negative means unlimited (not "delete all"), Render defaults to
  500 MB, explicit values are honoured, nothing is deleted when eviction is disabled, the oldest
  files are evicted when bounded, and the newest file is never evicted.
- `services/historical_service.py` — eviction policy reworked (see "Bug fix" above), plus a
  `_write_cache_file()` helper that keeps the running size estimate in sync.
- `.gitignore` — **new**. Ignores `migration_state.json`, `__pycache__/`, `.DS_Store`.
- `TASK_5_SUMMARY.md` — **new**. Full Task 5 write-up.
- `docs/cache-migration/CACHE_MIGRATION_TASKS.md`, `docs/cache-migration/CACHE_MIGRATION_HANDOFF.md`,
  `docs/cache-migration/CACHE_MIGRATION_DECISIONS.md`, `docs/DATA_AND_CACHE.md`,
  `docs/ARCHITECTURE.md` — updated.

## Tests
- `tests/test_migrate_cache_to_r2.py` — 22 tests, all pass (0.3s).
- `tests/test_r2_service.py` — 15 tests, all pass.
- `tests/test_cache_eviction_policy.py` — 11 tests, all pass.
- Full suite (`python -m unittest discover -s tests`): **58 tests, 52 pass, 5 failures + 1 error**
  (re-run 2026-11-07; the cache stayed at 1013 files before and after the run).
  Those 6 are **identical to the pre-existing baseline** before this work (verified by running the
  suite from a pristine `HEAD` worktree: 21 tests, same 5 failures + 1 error). They are
  Task 4 test-harness defects, not regressions:
  - `tests/test_cache_efficiency.py` and `tests/test_task4_verification.py` patch
    `services.r2_service.get_object` and `services.upstox_service.get_expired_historical_candles`,
    but `services/historical_service` imports those names directly
    (`from services.r2_service import get_object`). The patches therefore never apply, the real
    functions run, and the assertions see zero mock calls. The fix is to patch the *importing*
    module (`services.historical_service.get_object`) instead.
  - The same wrong-target patching makes those two tests attempt a real network call to the
    configured R2 endpoint. The suite only stays fast because an earlier test leaves a mocked
    client in the `services.r2_service._s3_client` singleton. Clearing that singleton makes the
    suite take ~50s. Worth fixing in the same pass.
  - `test_bounded_local_cache_eviction` asserts against `get_cache_stats()` while `CACHE_DIR` is
    a `MagicMock`, so `CACHE_DIR.glob()` iterates nothing and the stats are always zero.
- End-to-end check through the real botocore code path with a stubbed transport: upload wrote
  the expected keys and checksum metadata, `--verify` reported count match, byte match and 2/2
  checksums verified (PASS), and the local files were byte-identical afterwards.

## Data-loss incidents (resolved)
Two incidents deleted local cache data. Both causes were fixed and the owner has a backup.
1. **2026-10-20 — test suite.** `tests/test_historical_service.py` did not redirect the cache
   directory, so the production eviction helper ran against the real cache while the suite-wide
   `MAX_CACHE_SIZE_MB=1` setting was in effect. The files were recovered intact from the Git index.
   The test now isolates the cache directory, and a full test run is verified to leave the cache
   untouched.
2. **2026-10-26 — production cache cap.** See "Cache policy fix" above. The cap is now Render-only.

Keep the staged `historical_cache/` files in the Git index: they acted as the recovery source.

## Known limitations
- The migration covered every file present in `historical_cache/`. A scan found 483 files
  under 64 KiB whose candle lists were all empty (273 from 2024, 116 from 2025, and 94 from
  2026). The migration verified the existing bytes. Coverage of individual trading days
  depends on the source cache.
- The utility uploads whole-day pickle files. Objects larger than the boto3 multipart threshold
  get a multipart ETag, which is why checksums are stored as object metadata rather than relying
  on the ETag.
- Adding a new contract to a day re-uploads that whole day object, so incomplete days in R2 are
  expensive to complete. Non-trading days are cached as empty on purpose; an empty day downloaded
  during an API hiccup would stay empty permanently, and `--verify` cannot detect that.
- Two visitors fetching different contracts for the same day can race on the read-modify-write of
  the day object; the last write wins and one contract's entry can be dropped, causing at most one
  extra Upstox fetch.
- `backtest_results/` was not touched, migrated, or changed.
- The pre-existing Task 4 test failures listed above are still open.
- Pickle deserialization remains unsafe for untrusted objects; the bucket must stay private and
  write-restricted. Upstox's terms on retaining and sharing market data are still unconfirmed.
