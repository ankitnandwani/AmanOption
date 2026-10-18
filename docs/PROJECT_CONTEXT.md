# AmanOptions — Project Context

## Repository and deployment
- GitHub repository: https://github.com/ankitnandwani/AmanOption
- Project name: AmanOptions
- Language/runtime: Python (known from prior project discussions; exact Python version should be verified in project config).
- Web application: NiceGUI has been used in the project based on prior debugging context; verify the current implementation before changing UI code.
- Hosting: Render Free Web Service, according to the owner.
- Market-data provider: Upstox.
- Main product capability: options strategy backtesting over a selected date or date range.

## What the owner is building
AmanOptions is an options-trading/backtesting application. The user can run backtests, including multi-day backtests using a start date and end date. Historical market data is expensive/large enough that the application caches data by date and reuses it in later runs.

The intended experience is that multiple visitors can use the same shared historical cache, rather than each visitor separately rebuilding the same history from Upstox.

## Known user-facing behavior from prior discussions
- The application has had single-day and multi-day backtesting functionality.
- Multi-day backtests process dates in a range and produce backtest results.
- The user has previously debugged Render websocket timeouts during longer backtests. A small `time.sleep(0.001)` at an iteration point was reported to help; do not add, remove, or generalize this behavior without inspecting current code and understanding the event loop / websocket issue.
- A backtest result model was previously discussed as containing daily results (for example, a `BacktestResult` with `days` and `DayResult(date, pnl)`), but the exact current model should be verified.
- Prior context mentions event subscriptions and a worker/queue approach for multi-day backtests. Treat exact names and implementation as unverified until inspected.

## Large local data directories
The owner reports that these directories exist locally but are absent from GitHub because they contain data files:
- `historical_cache/`
- `backtest_results/`

The cache directory reportedly contains 962 `.pkl` files totalling approximately 3.14 GB. Do not infer that `backtest_results/` has the same contents or size. Its contents and retention needs have not yet been documented.

These directories are part of the local working environment, but their absence from GitHub means a fresh clone or Render deployment cannot be assumed to contain them. The cache hosting/migration approach is still being designed.

## Important unknowns
The following should be discovered only when relevant to a task:
- Actual source entry point and app startup command.
- Actual module and function names for cache read/write, Upstox calls, and backtest execution.
- Current cache file naming, folder layout, pickle schema, and whether the files contain raw candles, options chains, derived values, or other structures.
- Whether `backtest_results/` contains user-visible outputs, intermediate artifacts, logs, or reusable cache data.
- Existing tests, dependency manager, Python version, and deployment configuration.
- Whether there is already a storage abstraction or existing cache invalidation/expiry behavior.

## Agent guidance
Use this document to avoid rediscovering high-level context each session. Before changing code, inspect only the implementation paths relevant to the current task and update this document if the owner confirms new facts.
