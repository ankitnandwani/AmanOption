# AmanOptions — Known Architecture (Working Notes)

This is a high-level map based on prior project discussions. It is intentionally not a claim that every component name below exists in the current checkout.

## Logical components

1. **Web UI**
   - The app has backtest functionality and has used NiceGUI.
   - UI collects strategy/backtest configuration and displays progress/results.
   - Long backtests need to keep the UI responsive and handle progress/event updates.

2. **Backtest orchestration**
   - Supports a single date and a date range.
   - A multi-day run iterates through dates and aggregates daily outcomes.
   - Prior debugging mentioned a worker/queue approach and event subscription for progress. Verify the current code before changing concurrency or event handling.

3. **Strategy/backtesting engine**
   - Executes the selected strategy for the requested date(s).
   - Produces backtest outcomes, including daily P&L in previously discussed model examples.
   - Do not alter strategy calculations as part of a cache-storage migration.

4. **Market-data access**
   - Uses Upstox when required historical data is not already cached.
   - Existing behavior is date-oriented: cache hit means reuse; cache miss means fetch and persist.
   - Exact data format and API calls must be read from code.

5. **Local historical cache**
   - The owner has a local `historical_cache/` directory with approximately 962 `.pkl` files totalling about 3.14 GB.
   - These files are not in GitHub.
   - This directory currently acts as a local source of historical data, based on owner-provided context.

6. **Backtest results / artifacts**
   - The owner has a local `backtest_results/` directory not present in GitHub because it contains data files.
   - Purpose, format, size, and whether it is necessary at runtime are not yet confirmed.

7. **Hosting**
   - The app is deployed on Render Free Web Service.
   - Treat local filesystem storage on Render Free as ephemeral.
   - A durable external cache is being considered so that all visitors share data.

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
