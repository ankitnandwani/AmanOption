# Cache Migration Decisions

Record confirmed decisions here. Distinguish decided items from proposals.

## Confirmed by owner
- [Confirmed] The app runs on Render Free Web Service.
- [Confirmed] The cache is shared across all visitors.
- [Confirmed] The local cache has approximately 962 `.pkl` files totalling approximately 3.14 GB.
- [Confirmed] Local `historical_cache/` and `backtest_results/` directories are not in GitHub because they contain data files.
- [Confirmed] The current cache behavior checks local data first and fetches from Upstox on a miss.

## Confirmed by implementation (verified against the code)
- [Confirmed] The local cache is never evicted outside Render. `MAX_CACHE_SIZE_MB` is resolved
  once at import: unset means unlimited locally and 500 MB on Render (detected via
  `RENDER=true`, which Render always sets); an explicit value is honoured; `0` or negative means
  unlimited. A development machine must not silently delete downloaded market data.
- [Confirmed] Eviction order is by modification time, and the most recently written file is
  never evicted.
- [Confirmed] R2 object key layout is `historical_cache/{day_key}.pkl`, where `day_key` is
  `YYYY-MM-DD` for a single day and `from_date_to_date` for a range. Defined once in
  `services/cache_keys.py` and used by both `services/historical_service.py` and
  `migrate_cache_to_r2.py`. The first migration implementation used the bare file name as the
  object key, which would have made every migrated object unreachable by the application.
- [Confirmed] The bucket is read from `R2_BUCKET_NAME` by the application
  (`services/historical_service.py`, default `amanoptions-historical-cache`). The migration
  tool accepts `R2_BUCKET_NAME` and, for compatibility, `R2_BUCKET`.
- [Confirmed] Credentials come from `R2_ENDPOINT`, `R2_ACCESS_KEY_ID` and
  `R2_SECRET_ACCESS_KEY` for both the application and the migration tool.
- [Verified in Task 6] The migration target was `aman-options`. The live run used the
  account-level HTTPS endpoint with the bucket supplied separately and `AWS_DEFAULT_REGION=auto`.
- [Confirmed] The local cache is complete and backed up by the owner. The tool migrates whatever is
  present in `historical_cache/`.
- [Confirmed] Checksums are recorded as R2 object metadata (`md5`, `sha256`, `source-name`,
  `source-size`) at upload time rather than relying on the ETag, because objects uploaded
  through the multipart path have an ETag that is not an MD5 digest.

## Current recommendations / proposals
- [Proposed] Use Cloudflare R2 as private durable shared storage.
- [Proposed] Keep a bounded temporary local cache on Render.
- [Proposed] Use local cache → R2 → Upstox fallback.
- [Proposed] Use resumable migration and verify the existing data before cutover.
- [Proposed] Keep large data files and secrets out of Git.

## Rationale
- GitHub should hold source and documentation rather than a multi-gigabyte changing cache.
- Render Free local storage should not be treated as durable.
- R2 object storage avoids paying for outbound data transfer under its standard published pricing model, but account pricing/limits should be checked before implementation.
- A bounded local cache can reduce repeat downloads while allowing the full cache to live externally.
- A single shared key-layout module prevents the application and the migration tool from
  silently disagreeing about object names.

## Cutover and retention decisions (2026-11-12)

- [Verified] Render serves the app with `aman-options/historical_cache/` as the
  shared market-data cache. Keep the local originals, owner backup, and staged
  recovery files until the owner explicitly approves removal.
- [Decision for this migration] Keep `backtest_results/` on the existing
  filesystem. It supplies UI history and job status, while backtests use the
  historical candle cache as input. Hosted history can disappear when the Free
  service restarts, redeploys, or spins down. Durable history would require a
  separate decision about retention and who can see saved results.
  [Render Free filesystem behavior](https://render.com/docs/free#local-files-lost-on-redeploy)
- [Optional cleanup] Two objects outside the canonical prefix contain no unique
  contract keys or differing nonempty candle series. The handoff names the two
  keys for review. Removal requires approval for those exact objects.

## Open decisions
- Whether to use direct in-memory retrieval, temporary-file download, or a combination for each pickle.
- Local cache size and eviction policy.
- Whether controlled concurrent prefetching is needed after measuring actual multi-day performance.
- Upstox permission for retained/shared use of market data.
- Whether R2's default CRC32 request checksum is accepted by the target bucket; the client is
  currently configured not to send it, which is the conservative choice.
