# Cache Migration Decisions

Record confirmed decisions here. Distinguish decided items from proposals.

## Confirmed by owner
- [Confirmed] The app runs on Render Free Web Service.
- [Confirmed] The cache is shared across all visitors.
- [Confirmed] The local cache has approximately 962 `.pkl` files totalling approximately 3.14 GB.
- [Confirmed] Local `historical_cache/` and `backtest_results/` directories are not in GitHub because they contain data files.
- [Confirmed] The current cache behavior checks local data first and fetches from Upstox on a miss.

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

## Open decisions
- Exact R2 bucket/object-key layout after inspecting existing filenames.
- Whether to use direct in-memory retrieval, temporary-file download, or a combination for each pickle.
- Local cache size and eviction policy.
- Whether controlled concurrent prefetching is needed after measuring actual multi-day performance.
- What `backtest_results/` contains and whether it needs external persistence.
- Upstox permission for retained/shared use of market data.
