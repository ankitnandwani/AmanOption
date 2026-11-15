# Cloud backtest history handoff

## Status

Tasks 1 and 2 are complete. Cloud history browsing is ready for review at Git
baseline `7e819b9` plus the Task 2 working-tree changes. The owner confirmed
Cloudflare R2 for report storage. Production validation and enablement are
pending in [Task 3](TASKS.md).

## Task 2 implementation and checks

- `services/backtest_report_service.py` lists private report keys in pages of
  up to 20 using the R2 continuation token. Newest reports sort first by key.
  Selecting an entry reads a single object and validates its v1 identity,
  timestamps, and daily P&L. The reader caps JSON at 2 MiB. It reconstructs
  aggregates from validated daily rows, as the local renderer does.
- `ui/ui.py` uses the shared-history flag to choose the catalog. Cloud calls
  run off the event loop. The cloud view has loading, empty, retry, missing,
  and invalid states. The multi-day form discloses shared visibility before
  the run. A zero-day result displays its summary without best and worst days.
- `tests/test_backtest_report_service.py` covers bounded listing, continuation,
  selected-report reads, and invalid or missing objects. The isolated
  `unittest` run passed all 60 tests across `test_backtest_report_service`,
  `test_migrate_cache_to_r2`, `test_r2_service`, `test_historical_service`, and
  `test_cache_eviction_policy`.
- An in-process NiceGUI check drove the actual button callbacks across two
  client contexts with mocked storage, verifying loading, lazy details,
  continuation, unavailable and retry states, empty history, invalid and
  missing reports, independent panels, and legacy local results. Strategy
  and Upstox mocks received zero calls. Live R2 and Render were outside this run.
- Existing staged environment, IDE, and recovery data files were kept intact.

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
Check Git status and review Task 2 changes. For Task 3, first confirm the
production audience and approved report fields. Verify the private bucket
and report prefix with a synthetic report, then deploy only the reviewed
source changes. Verify report persistence across a Render restart and
compare summary and daily P&L in a fresh browser. Record the result and
rollback steps here and stop for review.
