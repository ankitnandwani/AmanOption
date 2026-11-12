# AmanOptions — Known Architecture (Working Notes)

This is a high-level map based on prior project discussions. It is intentionally not a claim that every component name below exists in the current checkout.

## Logical components

1. **Web UI** (`ui/ui.py`)
   - Built with NiceGUI.
   - Collects strategy/backtest configuration (access token, underlying, lots, target, SL, max loss) and mode (live, singleDayBacktest, multiDayBacktest).
   - Displays real-time positions, P&L, and logs.
   - For backtest modes, runs backend workers and shows results/history.

2. **Backtest orchestration**
   - Single-day backtest: `ui.py` → `run_backtest_worker` → `backtest.backtest.start_backtest` → `Backtester.prepare_day` → returns (`strategy`, `historical`) where `historical` is a dict mapping `instrument_key` → list of `Candle` objects; then runs strategy via `strategy.run_backtest(historical)`.
   - Multi-day backtest: `ui.py` → `run_multiday_worker` → `Backtester.run_date_range` → loops through dates, calling `prepare_day` for each date and accumulating `DayResult` objects.
   - Uses event bus (`models/events.py`) for progress updates to UI.

3. **Strategy/backtesting engine** (`strategy.py`)
   - `Strategy` class manages state, market data, and executes trading logic.
   - `run_backtest` delegates to `bootstrap_backtest` (strategy_service) and `run_replay` (replay_engine).
   - Does not alter P&L calculations during cache migration.

4. **Market-data access**
   - Core caching in `services/historical_service.py`: `get_historical_candles`.
   - Cache key: per-date (or per date range) pickle file `historical_cache/{from_date}_{to_date}.pkl` when `from_date != to_date`, otherwise `historical_cache/{from_date}.pkl`; each file contains a dict mapping `instrument_key` → list of `Candle` objects.
   - On cache miss, calls `services/upstox_service.get_expired_historical_candles` (Upstox SDK).
   - `backtest/historical_market_data.load_historical_market_data` orchestrates fetching for all contracts for a date (or date range) by calling `get_historical_candles` per instrument.

5. **Local historical cache**
   - Directory: `historical_cache/` (git-ignored).
   - One `.pkl` file per calendar date, each holding ~211 instrument keys mapped to lists of
     `Candle` objects (from `models/models.py`); the full dataset is ~3 GB.
   - Bounded by `MAX_CACHE_SIZE_MB`: `_enforce_cache_size_limit()` deletes the least recently
     written files when the directory exceeds the limit. The limit is resolved once at import
     time: unlimited by default outside Render, 500 MB on Render (`RENDER=true`), `0`/negative
     meaning unlimited, an explicit value being honoured as-is. This runs against the real
     directory, so tests must redirect `CACHE_DIR` to a temporary path.
   - Eviction is throttled to at most one directory scan every 5 seconds, and the most recently
     written file is never evicted.

6. **Backtest results / artifacts**
   - Directory: `backtest_results/` (git-ignored).
   - Stores per-job JSON results (`backtest_results/<job_id>.json`) and status files (`.status`).
   - Contains aggregated backtest outcomes (total P&L, win rate, daily P&L, etc.) for display in UI history.

7. **Hosting**
   - Deployed on Render Free Web Service.
   - Local filesystem treated as ephemeral; not durable across redeploys.
   - External cache (e.g., Cloudflare R2) needed for shared persistence across users.

8. **Cache key layout (`services/cache_keys.py`)**
   - Single source of truth for both the local file name and the R2 object key, shared by
     `services/historical_service.py` and `migrate_cache_to_r2.py`.
   - Local file: `historical_cache/{day_key}.pkl`; R2 object key: `historical_cache/{day_key}.pkl`.
   - Bucket: `R2_BUCKET_NAME` (default `amanoptions-historical-cache`).
   - Credentials: `R2_ENDPOINT`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`.

9. **R2 storage adapter (`services/r2_service.py`)**
   - `get_client()`, `object_exists()`, `get_object()`, `put_object()` (optional `metadata`),
     `put_file()` (managed streaming upload), `head_object()`, `list_objects()` (paginated).
   - The client is configured with `request_checksum_calculation="when_required"`: recent
     botocore versions attach a CRC32 `ChecksumAlgorithm` to every `PutObject` by default,
     which Cloudflare R2 does not reliably accept.

10. **Migration utility (`migrate_cache_to_r2.py`)**
    - Modes: `--list`, `--dry-run`, `--upload` (default), `--verify`.
    - Resumable through `migration_state.json` (git-ignored); retries with exponential backoff.
    - Stores MD5/SHA-256 as object metadata so verification does not depend on the ETag.
    - Never modifies or deletes the local cache files.

## Target cache architecture under consideration

The current preferred proposal is private Cloudflare R2 object storage plus a bounded Render-local cache:

1. Backtest requests a date's market data.
2. Check local temporary cache first.
3. If absent locally, retrieve the matching object from R2.
4. Store it in local cache if useful and load it.
5. If absent from R2, use the existing Upstox code to fetch it.
6. Validate the fetched result, upload it to R2, and use it for the current run.
7. Reuse cached data for later dates and requests.

Do not implement this proposal unless it is approved and the task tracker indicates the current task. The storage interface, object key layout, retries, cache eviction, concurrent misses, and failure behavior still need to be designed against the actual code.

## Non-goals for cache migration
- Rewriting the strategy engine.
- Changing P&L calculation.
- Redesigning the UI.
- Migrating unrelated output folders without first understanding their purpose.
- Uploading secrets or data files to GitHub.
