# Cloud backtest history handoff

## Status

Tasks 1 and 2 are complete and committed. The local history implementation and
GitHub's `nicegui` branch match at `1cb1cdb`. [Task 3](TASKS.md) is complete.
Source and R2 checks passed. The owner approved the shared audience and report
fields on 2026-11-16. Cloud history is enabled on Render and report persistence
was verified on 2026-11-17.

## Task 3 preflight

- Verified that `0e85fea..1cb1cdb` changes only source, tests, and documentation.
  The unrelated staged environment, IDE, market-cache, and report files were
  preserved. This session made no commit, push, or Render configuration change.
- Reran the five targeted suites listed below in a temporary working directory
  with R2 credentials removed from the test environment. All 60 tests passed.
- Used the local R2 credentials to save one synthetic v1 report in
  `aman-options` under `backtest_results/v1/`, find it in the first history
  page, and read it through the application service. The saved daily P&L
  values of ₹12.50 and −₹4.00 matched on read, for a total of ₹8.50.
  The unsigned S3 GET returned HTTP 400 `InvalidArgument`. The synthetic
  object was removed and HEAD returned HTTP 404 afterward.
- The local `.env.local` endpoint includes a bucket suffix. The live probe
  succeeded with the account-level HTTPS endpoint and `AWS_DEFAULT_REGION=auto`
  passed only to the probe process. Leave local credentials intact. Verify
  the effective Render endpoint and region before setting the history flag.
- The owner confirmed that all app visitors may see new completed
  reports and that the approved fields are job ID, UTC completion time,
  requested date range, summary metrics, and daily dates and P&L. The schema
  version is stored alongside those fields. Strategy inputs remain outside
  the report envelope.
- Reran the same isolated targeted suites after approval. All 60 tests passed.

## Task 3 rollout and rollback

- Render was already on the reviewed `nicegui` commit `1cb1cdb`. Verified
  the account-level R2 endpoint, `aman-options` bucket, and `auto` region.
  Added `BACKTEST_CLOUD_HISTORY=true`. The
  [configuration deploy](https://dashboard.render.com/web/srv-d99tuvks728c73dsjso0/deploys/dep-dbtjgtp5efls73fb52s0)
  succeeded and is live at the same revision. The multi-day form displayed
  the shared visibility notice, and a separate session loaded the empty
  shared catalog successfully.
- Started two validation jobs with the default Render token and strategy
  settings. November 2–3 used
  `job_20261116_171036_577916ffcf30445aaa8ec3c16b9729cd`. October 26–27 used
  `job_20261116_171334_b328771b7b9c4cb381c7a3a394701890`. Both were still
  processing their first day at the initial check. The November 2–3 job
  subsequently appeared in shared history.
- The owner ran `job_20261117_110705_5099187d54f2480baac734a4b239ac32`.
  A fresh visitor session listed it with completion time 2026-11-17 11:18:21 UTC
  and opened the saved report. Render confirmed a successful service restart.
  A second fresh visitor session reopened the same job, with matching P&L
  on September 21 (₹581.75) and September 22 (₹1,933.75), a total of
  ₹2,515.50, and a 100% win rate. Both sessions used View History without
  entering an Upstox token or rerunning the backtest.

To roll back, set `BACKTEST_CLOUD_HISTORY=false` in the Render service's
Environment settings and choose **Save and deploy**. Verify View History uses
the local catalog and leave existing R2 reports in place.
[Render environment settings](https://render.com/docs/configure-environment-variables)

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
The rollout and persistence checks are complete. Stop for owner review.
Record the live revision, fresh-browser and restart evidence, and any
rollback needed. Stop for review.
