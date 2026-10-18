# AmanOptions — Data, Cache, and Storage Notes

## Known current state
- Local `historical_cache/` exists but is absent from GitHub.
- Owner reports about 962 `.pkl` files and 3.14 GB in this directory.
- The current cache behavior is described as: for a requested date, use the local cached file if it exists; otherwise fetch historical data through Upstox and save it for later reuse.
- Local `backtest_results/` also exists and is absent from GitHub because it contains data files. Its precise purpose and retention policy are not yet known.
- The cache is intended to be shared across all application visitors.
- Deployment is on Render Free Web Service, whose local filesystem must not be treated as durable storage.

## Recommended direction (not yet implemented unless verified in code)
Use Cloudflare R2 as the durable shared cache and a bounded local cache on Render for performance.

### Expected read flow
1. Request data for a date.
2. Check the local temporary cache.
3. If a valid local entry exists, use it.
4. Otherwise check the corresponding object in private R2.
5. If R2 has the object, download only that requested object (or a controlled prefetch batch), then use it.
6. If neither local cache nor R2 has it, call the existing Upstox integration.
7. Validate the fetched data, save it locally as appropriate, upload it to R2, and return it to the backtest.

### Multi-day backtests
- Do not download the whole bucket at startup.
- Avoid duplicate reads/deserialization for the same date during a run.
- Use bounded local disk caching; Render Free local disk is ephemeral and capacity should not be assumed.
- If profiling shows serial object reads are too slow, consider limited concurrency or batch prefetching.
- Avoid unbounded in-memory storage for long ranges.
- Consider two visitors requesting the same uncached date simultaneously. Prevent duplicate Upstox fetches where practical and make uploads safe/idempotent.
- Define how to handle partial/corrupt downloads, R2 outages, Upstox errors, and upload failures without silently returning invalid data.
- Keep local and R2 cache key naming compatible with the current code unless a deliberate migration is approved.

## Migration requirements
- Preserve the original local files until migration is verified.
- Use a resumable upload process; do not require a single fragile upload of all 962 files.
- Verify uploaded object count, total bytes, representative file sizes, and checksums where feasible.
- Test a known cache hit and a known cache miss.
- Confirm a cache miss fetches from Upstox and persists a reusable object.
- Confirm repeated requests do not repeatedly fetch or download the same data unnecessarily.
- Confirm existing backtest results remain equivalent for representative dates.
- Keep R2 credentials in Render environment variables; never commit them.

## Pickle safety and market-data rights
- Python pickle files can execute code when deserialized. Only load data from the trusted migration/fetch pipeline and restrict write access to the bucket. Consider integrity checks and versioned metadata.
- The owner should verify that Upstox's applicable terms permit retaining historical market data and making it available through a multi-user application.

## Open questions to resolve from the actual project
- Are cache files one per date, one per instrument/date, or keyed some other way?
- What exact structure and schema is serialized?
- Does the app need `backtest_results/` on Render, or is it only local analysis output?
- Is there any current cache expiration, invalidation, or data-versioning rule?
- What local cache size/eviction policy fits Render Free constraints?
