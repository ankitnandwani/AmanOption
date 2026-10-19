# AmanOptions — Data, Cache, and Storage Notes

## Known current state
- Local `historical_cache/` contains 962 `.pkl` files (one per trading day) totalling approximately 3.14 GB.
- Each file is named `{from_date}_{to_date}.pkl` when `from_date != to_date`, otherwise `{from_date}.pkl` (format YYYY-MM-DD). It contains a pickle-serialized dict mapping `instrument_key` (string) to a list of `Candle` objects (from `models.models`).
- The current cache behavior: for a requested date range (`from_date`, `to_date`), if the corresponding pickle file exists, load the dict and return the list for each instrument key; otherwise fetch from Upstox for each instrument and save the dict to the pickle file. For single-day requests (`from_date` == `to_date`), the file is named `YYYY-MM-DD.pkl`.
- Local `backtest_results/` contains per-job JSON result files and status files; used to store backtest outcomes for UI history, not required for runtime backtesting.
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

## Resolved questions
- Cache files are one per date (YYYY-MM-DD.pkl), not per instrument/date.
- Serialized structure: a dict mapping instrument_key → list of Candle objects (from models.models), where Candle has fields: timestamp (datetime), open, high, low, close (float), volume (int), oi (int).
- The app does not need `backtest_results/` on Render for runtime backtesting; it stores per-job JSON results for UI history only.
- No current cache expiration, invalidation, or data-versioning rule; cached data is considered valid indefinitely.
- Local cache size/eviction policy: to be determined as part of the migration (e.g., LRU with size limit appropriate for Render Free constraints).
