# Cloud backtest history handoff

## Status

Task 1 is complete and ready for review. The owner confirmed Cloudflare R2 as
the provider for report storage. [Task 2](TASKS.md) covers browsing saved
reports. Keep production enablement for Task 3.

## Task 1 implementation

- `services/backtest_report_service.py` writes the existing local JSON shape
  atomically. With `BACKTEST_CLOUD_HISTORY=true` and an explicit
  `R2_BUCKET_NAME`, it also writes version 1 JSON to
  `backtest_results/v1/<18-digit reverse UTC microseconds>_<job_id>.json`.
  The timestamp is the number of microseconds from completion to UTC
  `datetime.max`. The job ID combines a UTC timestamp with a UUID.
- The envelope contains `schema_version`, `job_id`, `completed_at`,
  `start_date`, `end_date`, and `result`. Only the legacy summary and daily P&L
  fields populate `result`. Strategy configuration is outside the envelope.
- `services/r2_service.py` exposes the existing client construction so the
  report PUT can use 3-second connect and 5-second read timeouts and two SDK
  attempts with the same key and body. Market-data callers keep their existing
  singleton and settings.
- `ui/ui.py` saves from the multi-day worker. The completed result and status
  survive a failed upload, and the UI displays a separate warning. The legacy
  history reader still displays local reports. No live R2 writes or Render
  deployment were performed during Task 1.
- All 57 targeted tests passed in an isolated working directory. This includes
  five new report tests and a transport stub that exercises the real botocore
  retry handler. A separate in-process check built two NiceGUI client contexts,
  verified distinct completion queues, and confirmed local history and result
  rendering after a simulated cloud failure. The six known cache test-harness
  failures were outside this run.

## Verified starting points

- `ui/ui.py` contains `run_multiday_worker`,
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
Check Git status. Implement Task 2 with mocked R2 and temporary results paths.
Use the existing feature flag, fetch one history page at a time, and load and
validate report details on selection. Preserve the local history path and add
the shared-history disclosure before production enablement. Record actual
changes and `unittest` results here and stop for review.
