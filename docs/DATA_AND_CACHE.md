# AmanOptions — Data, Cache, and Storage Notes

## Known current state
- Local `historical_cache/` contains one `.pkl` file per calendar date (~3 GB in total, complete
  locally with an owner-held backup). Each file holds ~211 instrument keys.
- Each file is named `{from_date}_{to_date}.pkl` when `from_date != to_date`, otherwise `{from_date}.pkl` (format YYYY-MM-DD). It contains a pickle-serialized dict mapping `instrument_key` (string) to a list of `Candle` objects (from `models.models`).
- The current cache behavior: for a requested date range (`from_date`, `to_date`), if the corresponding pickle file exists, load the dict and return the list for each instrument key; otherwise fetch from Upstox for each instrument and save the dict to the pickle file. For single-day requests (`from_date` == `to_date`), the file is named `YYYY-MM-DD.pkl`.
- A cached empty response is treated as a valid hit on purpose, so non-trading days do not trigger repeated API calls.
- Local `backtest_results/` contains per-job JSON result files and status files; used to store backtest outcomes for UI history, not required for runtime backtesting.
- The cache is intended to be shared across all application visitors.
- Deployment is on Render Free Web Service, whose local filesystem must not be treated as durable storage.

## Cache key layout (verified against the code)
- Local file: `historical_cache/{day_key}.pkl`.
- R2 object key: `historical_cache/{day_key}.pkl` — the same relative path under the prefix.
- Both the application and the migration tool derive this from `services/cache_keys.py`
  (`R2_KEY_PREFIX`, `cache_file_name()`, `r2_object_key()`), so the two cannot drift apart.
- Bucket name comes from `R2_BUCKET_NAME` (default `amanoptions-historical-cache`).
  The migration tool also accepts `R2_BUCKET`.
- Credentials come from `R2_ENDPOINT`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`.

## Recommended direction
Use Cloudflare R2 as the durable shared cache and a bounded local cache on Render for performance.
The R2 adapter, the app's read/write paths, and the migration utility are implemented.
The Task 6 migration on 2026-11-07 uploaded 1,013 pickle files totaling 3,340,758,071 bytes
to the `aman-options` bucket. Verification matched counts, bytes, per-object sizes, and
all 1,013 checksums. The local inventory included 483 files under 64 KiB with no nonempty
candle lists. The migration preserved those cached responses. Two multi-day backtests
matched the local baseline, and an isolated live miss persisted to R2 for reuse. See the
[migration handoff](cache-migration/CACHE_MIGRATION_HANDOFF.md).

On 2026-11-08, Task 7 reconciled the settled local delta and verified 1,029 objects
and 3,441,218,611 bytes in R2. All 1,029 checksums matched.

On 2026-11-11, the live Render backtest for November 2–3 matched the baseline.
The live October 8 fallback expanded its R2 object from 182 to 216 contracts
and preserved all original series.

On 2026-11-12, Task 8 verified that all 1,029 local cache keys had canonical
R2 objects. Only the enriched October 8 object differed in size. The cutover
retains the local originals and keeps backtest history on the current filesystem.
See the [migration handoff](cache-migration/CACHE_MIGRATION_HANDOFF.md).

### Expected read flow (implemented)
1. Request data for a date.
2. Check the local temporary cache.
3. If a valid local entry exists, use it.
4. Otherwise check the corresponding object in private R2.
5. If R2 has the object, download only that requested object (or a controlled prefetch batch), then use it.
6. If neither local cache nor R2 has it, call the existing Upstox integration.
7. Validate the fetched data, save it locally as appropriate, upload it to R2, and return it to the backtest.

## Cloudflare R2 economics for this dataset
Published R2 pricing (page updated 2026-10-01): storage $0.015/GB-month, Class A operations (writes)
$4.50/million, Class B operations (reads/HEAD) $0.36/million, **egress free**. Free tier per month:
10 GB-month storage, 1M Class A, 10M Class B.

At the current dataset size (~3 GB, ~1013 objects) everything sits inside the free tier: storage
$0, the migration's ~1013 PUTs $0, a full multi-day backtest's ~1013 GETs $0, and pulling the whole
dataset to Render $0 because egress is free. Even exceeding the free tier would only cost
$0.015/GB-month (about $0.06/month for 4 GB of overage).

## Known cache design caveats
- **One R2 object per day, holding ~211 instruments.** The app downloads a whole day object once and
  serves the remaining contracts from the local cache, so a full multi-day backtest costs ~1013 GETs
  rather than ~211,000. But adding a *new* contract to a day re-uploads the entire day object, so
  incomplete days in R2 are expensive to complete. Migrate complete days.
- **Non-trading days are cached as empty on purpose**, and the app treats an empty cached day as a
  hit — so a day downloaded during an API hiccup stays empty permanently. `--verify` detects
  truncated uploads but cannot distinguish "genuinely empty" from "the API returned nothing".
- **Lost-update race:** two visitors fetching different contracts for the same day can each read the
  day object and write it back; the last write wins and one contract's entry can be dropped. Worst
  case that one contract is re-fetched from Upstox once.

## Multi-day backtests
- Do not download the whole bucket at startup.
- Avoid duplicate reads/deserialization for the same date during a run.
- Use bounded local disk caching; Render Free local disk is ephemeral and capacity should not be assumed.
- If profiling shows serial object reads are too slow, consider limited concurrency or batch prefetching.
- Avoid unbounded in-memory storage for long ranges.
- Consider two visitors requesting the same uncached date simultaneously. Prevent duplicate Upstox fetches where practical and make uploads safe/idempotent.
- Define how to handle partial/corrupt downloads, R2 outages, Upstox errors, and upload failures without silently returning invalid data.
- Keep local and R2 cache key naming compatible with the current code unless a deliberate migration is approved.

## Migration utility
`migrate_cache_to_r2.py` uploads the local cache to R2.

```bash
export R2_ENDPOINT="https://<account_id>.r2.cloudflarestorage.com"
export R2_ACCESS_KEY_ID="..."
export R2_SECRET_ACCESS_KEY="..."
export R2_BUCKET_NAME="aman-options"
export AWS_DEFAULT_REGION="auto"

python migrate_cache_to_r2.py --list      # inventory local vs R2 (works without credentials)
python migrate_cache_to_r2.py --dry-run   # planned actions, no writes
python migrate_cache_to_r2.py --upload    # resumable upload
python migrate_cache_to_r2.py --verify    # count / bytes / size / checksum verification
```

- Resumable: per-file progress is recorded in `migration_state.json` (git-ignored) and rewritten
  after every file; objects that already exist with the expected size are skipped.
- Retries: `--retries` (default 3) with exponential backoff (`--backoff`, default 2s).
- Checksums: MD5 and SHA-256 are stored as R2 object metadata (`md5`, `sha256`, `source-name`,
  `source-size`) at upload time. Verification compares the stored MD5 against the local MD5.
  A plain-MD5 ETag is used as a fallback; a multipart ETag is reported as unverifiable rather
  than as a mismatch.
- The local files are only read. The tool contains no delete/unlink/remove call.

## Migration requirements
- Preserve the original local files until migration is verified.
- Use a resumable upload process; do not require a single fragile upload of all 1013 files.
- Verify uploaded object count, total bytes, representative file sizes, and checksums where feasible.
- Test a known cache hit and a known cache miss.
- Confirm a cache miss fetches from Upstox and persists a reusable object.
- Confirm repeated requests do not repeatedly fetch or download the same data unnecessarily.
- Confirm existing backtest results remain equivalent for representative dates.
- Keep R2 credentials in Render environment variables; never commit them.

## Local cache eviction policy
The local cache is the only place downloaded market data lives before it is uploaded to R2, so
deletion is opt-in, never the default.

`services/historical_service.py` resolves `MAX_CACHE_SIZE_MB` once, at import time:

| `MAX_CACHE_SIZE_MB` | Result |
|---|---|
| unset, not on Render | **Unlimited** — no cache file is ever deleted |
| unset, on Render (`RENDER=true`) | 500 MB — the least recently written files are deleted above the limit |
| greater than 0 | That many megabytes; files above the limit are evicted |
| `0` or negative | **Unlimited** — eviction disabled |

- Render always sets `RENDER=true`, so the deployed service keeps a bounded local cache without
  any configuration. Set `MAX_CACHE_SIZE_MB` explicitly in the Render dashboard as well.
- Outside Render the default is unlimited, so downloading data for a new year never destroys
  previously downloaded data.
- Eviction order is by **modification time** (least recently written first), not access time:
  access times are unreliable across filesystems and are frequently not updated at all.
- The most recently written file is never evicted — it is the work that was just done.
- Eviction is logged: `Evicted N cache file(s), freed X MB to stay within the Y MB local cache limit`.
- Scans are throttled (at most once every 5 seconds) because the check runs after every contract
  write and a full directory scan per write is expensive.

## Test-suite safety
- The test suite must never point the cache layer at the real `historical_cache/` directory.
  `services.historical_service._enforce_cache_size_limit()` deletes real files when the cache
  exceeds `MAX_CACHE_SIZE_MB`, and that limit is read from the environment at import time.
  `tests/test_historical_service.py` redirects `CACHE_DIR` to a temporary directory and disables
  eviction for the duration of the tests.
- If the cache directory is ever emptied unexpectedly, the files can be restored from the Git
  index (they are staged there): `git ls-files historical_cache | git checkout-index -f --stdin`.

## Pickle safety and market-data rights
- Python pickle files can execute code when deserialized. Only load data from the trusted migration/fetch pipeline and restrict write access to the bucket. Consider integrity checks and versioned metadata.
- The owner should verify that Upstox's applicable terms permit retaining historical market data and making it available through a multi-user application.

## Resolved questions
- Cache files are one per date (YYYY-MM-DD.pkl), not per instrument/date.
- Serialized structure: a dict mapping instrument_key → list of Candle objects (from models.models), where Candle has fields: timestamp (datetime), open, high, low, close (float), volume (int), oi (int).
- The app does not need `backtest_results/` on Render for runtime backtesting; it stores per-job JSON results for UI history only.
- No current cache expiration, invalidation, or data-versioning rule; cached data is considered valid indefinitely.
- A cached empty response is treated as a valid hit on purpose (weekends/holidays must not trigger repeated API calls).
- Local cache size/eviction policy: settled — unlimited on a development machine, 500 MB on Render,
  overridable with `MAX_CACHE_SIZE_MB`. See "Local cache eviction policy" above.
- R2 object key layout: `historical_cache/{day_key}.pkl`, defined in `services/cache_keys.py`.
