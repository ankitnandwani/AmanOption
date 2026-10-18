# Cache Migration Plan — AmanOptions

## Objective
Move the shared historical market-data cache from local-only storage to durable object storage, while keeping the existing backtest behavior and minimizing changes to the application.

## Starting facts
- Render plan: Free Web Service.
- Cache is shared across visitors.
- Local `historical_cache/`: approximately 962 `.pkl` files, approximately 3.14 GB.
- `historical_cache/` and `backtest_results/` are local-only directories and are absent from GitHub because they contain data files.
- Existing behavior: use a local cached file for a date if available; otherwise fetch from Upstox and save for reuse.
- Preferred storage candidate: Cloudflare R2 private bucket.
- The current design is a proposal; confirm actual code paths and file structure before implementing.

## Target behavior
For each required cache key:
1. Check the bounded local cache.
2. If present and valid, use it.
3. Otherwise retrieve the object from R2.
4. If R2 has it, optionally retain it in the local cache and use it.
5. If R2 does not have it, use the existing Upstox integration.
6. Validate the fetched result, write to local cache as appropriate, upload to R2, and use it.
7. Make repeated requests reuse stored data.
8. Handle concurrent requests for the same missing key without corrupting data or needlessly duplicating work.

## Constraints
- No whole-bucket download at startup.
- Render Free local filesystem is temporary, not durable.
- Do not commit market data or secrets to GitHub.
- Keep the cache private and credentials server-side.
- Preserve the existing pickle schema and cache-key convention unless migration proves a change is necessary.
- Do not alter strategy logic or P&L calculations.
- Keep original data until the migration is verified.
- Confirm Upstox retention/sharing permissions before serving shared cached data.

## Implementation approach
1. Inspect the current repository and document exact cache functions, call graph, file names, schemas, dependencies, and tests.
2. Add and unit-test an R2 storage adapter with mocked network interactions.
3. Integrate storage behind the existing cache interface.
4. Add tests for local hit, R2 hit, full miss / Upstox fetch, upload, repeated access, failures, and concurrent misses.
5. Design a bounded local cache and only add concurrent prefetching if measured to be useful.
6. Build a resumable uploader and migrate existing data.
7. Verify object count, bytes, checksums, and representative deserialization.
8. Deploy with secrets configured in Render and validate representative backtests.
9. Keep rollback possible until the new path is confirmed stable.

## Acceptance criteria
- Existing cached data can be read without refetching it from Upstox.
- A cache miss calls the existing Upstox path and stores the result in R2.
- A second request reuses the cached result.
- Multi-day backtests do not repeatedly download or deserialize the same date unnecessarily.
- Local storage and memory use remain bounded.
- R2 or provider errors are handled explicitly and safely.
- Representative backtest results match the pre-migration baseline.
- No secrets or large data files are committed.
