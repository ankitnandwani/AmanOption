# Cloud backtest history handoff

## Status

Planning is complete. The owner confirmed multi-day backtests run on Render and
requested durable reports and a way for visitors to browse prior results.
Implementation starts with [Task 1](TASKS.md). The [plan](PLAN.md) defines the
storage contract, visibility proposal, and acceptance checks.

## Verified starting points

- `ui/ui.py` contains `save_backtest_result`, `run_multiday_worker`,
  `load_backtest_results`, `show_history`, and `render_multiday_results`.
  The existing history reads all local JSON files and their status companions
  when opened. `models/backtest_result.py` defines the result model.
- `services/r2_service.py` already supports reading and writing bytes. Its
  `list_objects` is designed for migration inventory. Add bounded history
  paging without changing that method's behavior.
- The planning checkout was at `0e85fea` with staged local files, including
  `.env.local` and existing cache and report artifacts. Check Git again before
  editing or publishing. Stage only intended source and documentation paths.

## Decisions for review

- Proposed production audience is all app visitors, with shared visibility
  explained before running a backtest. Confirm before production enablement.
- Existing reports stay local unless the owner explicitly approves a reviewed
  import. Any import should validate the data, derive a stable key, and be safe
  to rerun. Existing reports lack requested date range and strategy settings,
  so leave unknown fields unknown.

## Next agent

Read `AGENTS.md`, the context docs, and the backtest history plan and tracker.
Check Git status. Implement Task 1 with mocked R2 and temporary results paths,
then record actual changes and test results here and stop for review. Use the
project's `unittest` workflow. The planning pass added documentation only and
validated its relative links and whitespace.
