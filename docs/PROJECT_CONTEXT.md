# AmanOptions — Project Context

## Repository and deployment
- GitHub repository: https://github.com/ankitnandwani/AmanOption
- Project name: AmanOptions
- Language/runtime: Python. The project venv is Python 3.14 (`.venv/`); `runtime.txt` pins `python-3.14`.
- Web application: NiceGUI. The entry point is `ui/ui.py`, which ends with
  `ui.run(title="Options Trading Bot", host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))`.
  The `Procfile` declares `web: python ui.py` while the module actually lives at `ui/ui.py` — verify
  the effective start command in the Render dashboard. Task 7 confirmed that the
  AmanOption service on `nicegui` uses `python -m ui.ui` and verified it locally.
- Dependencies (`requirements.txt`): nicegui, requests, upstox-python-sdk, protobuf,
  websocket-client, pandas, streamlit-autorefresh, boto3. There is no pytest and no dotenv
  integration, so tests run through `unittest` and environment variables must be set in the shell
  (locally) or in the Render dashboard (deployed).
- Hosting: Render Free Web Service (confirmed by the owner). Render always sets `RENDER=true`,
  which the app uses to detect a deployed environment.
- Market-data provider: Upstox.
- Main product capability: options strategy backtesting over a selected date or date range.

## What the owner is building
AmanOptions is an options-trading/backtesting application. The user can run backtests, including multi-day backtests using a start date and end date. Historical market data is expensive/large enough that the application caches data by date and reuses it in later runs.

The intended experience is that multiple visitors can use the same shared historical cache, rather than each visitor separately rebuilding the same history from Upstox. Upstox's historical availability is limited, so the shared cache is the durable copy and the API is the last resort.

## Known user-facing behavior from prior discussions
- The application has had single-day and multi-day backtesting functionality.
- Multi-day backtests process dates in a range and produce backtest results.
- The user has previously debugged Render websocket timeouts during longer backtests. A small `time.sleep(0.001)` at an iteration point was reported to help; do not add, remove, or generalize this behavior without inspecting current code and understanding the event loop / websocket issue.
- A backtest result model was previously discussed as containing daily results (for example, a `BacktestResult` with `days` and `DayResult(date, pnl)`), but the exact current model should be verified.
- Prior context mentions event subscriptions and a worker/queue approach for multi-day backtests. Treat exact names and implementation as unverified until inspected.

## Large local data directories
The owner reports that these directories exist locally but are absent from GitHub because they contain data files:
- `historical_cache/` — one `.pkl` file per calendar date, each holding ~211 instrument keys mapped
  to lists of `Candle` objects. The full dataset (~3 GB) is present locally and the owner keeps an
  independent backup of it. Treat the directory contents as the source of truth rather than any
  quoted figure.
- `backtest_results/` — per-job JSON results and status files for UI history. Not required for
  runtime backtesting; retention needs are not formally documented.

These directories are part of the local working environment, but their absence from GitHub means a
fresh clone or Render deployment cannot be assumed to contain them. Cloudflare R2 is the intended
durable home for the cache. On 2026-11-07, Task 6 uploaded 1,013 local pickle files totaling
3,340,758,071 bytes to R2 and verified all 1,013 checksums. See the
[migration handoff](cache-migration/CACHE_MIGRATION_HANDOFF.md).

## Verified implementation facts
These were confirmed against the code and can be relied on:
- Cache read/write lives in `services/historical_service.py` (`get_historical_candles`); the Upstox call is `services/upstox_service.get_expired_historical_candles`.
- `backtest/historical_market_data.load_historical_market_data` orchestrates fetching every contract for a date or date range by calling `get_historical_candles` per instrument.
- Cache file naming: `historical_cache/{from_date}_{to_date}.pkl` when the range is not a single day, otherwise `historical_cache/{from_date}.pkl`.
- Pickle schema: a dict mapping `instrument_key` → list of `Candle` objects (`models.models.Candle` with
  `timestamp` (datetime), `open`, `high`, `low`, `close` (float), `volume`, `oi` (int)).
- No cache expiration, invalidation or data-versioning rule: cached data is valid indefinitely, and a
  cached empty response is deliberately treated as a hit.
- The local cache is bounded on Render only (500 MB via `MAX_CACHE_SIZE_MB` / `RENDER=true`) and unlimited
  on a development machine.

## Important unknowns
The following should be discovered only when relevant to a task:
- The final environment variables configured for the Render deployment.
- Whether `backtest_results/` needs external persistence.
- Whether Upstox's terms permit retaining and sharing historical market data through a multi-user app.

## Agent guidance
Use this document to avoid rediscovering high-level context each session. Before changing code, inspect only the implementation paths relevant to the current task and update this document if the owner confirms new facts.
