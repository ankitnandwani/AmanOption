# Cloud backtest history

Render currently saves completed multi-day reports to `backtest_results/<job_id>.json`.
The existing **View History** reads that directory and uses the same result renderer
as the fresh run. Render Free discards its local files on restart, redeploy, or spin-down.
[Render filesystem behavior](https://render.com/docs/free#local-files-lost-on-redeploy)

## Proposed first release

Save new completed multi-day reports in private Cloudflare R2. Let visitors open
**View History**, browse recent reports, and select **View** to see the original
summary and daily P&L without rerunning the strategy or calling Upstox. Preserve
the immediate post-run result and existing local JSON output.

The proposed history is shared and read-only for app visitors. A private R2 bucket
keeps storage credentials server-side, while the app determines who can view reports.
Confirm the shared audience before enabling it in production. In shared mode, label
the history as shared and disclose before a multi-day run that its completed report
will be visible to other visitors. If the owner wants per-user visibility, define
authentication and ownership before enabling cloud history. Keep existing reports
local by default. Import only an explicitly reviewed set in a separate task.

## Storage and integration

- Use the existing private `aman-options` bucket and server-side R2 client, under
  `backtest_results/v1/`. Use one completed JSON report per run. Use collision-resistant
  job IDs and keys that sort newest first, such as an inverted fixed-width UTC
  completion timestamp followed by the job ID. Construct the key once per report
  and reuse it on retries. Leave `historical_cache/` and its migration tooling alone.
- Wrap the existing report in a versioned envelope with job ID, UTC completion
  time, requested date range, and the current result fields. Include underlying
  or strategy inputs only from an explicit approved field list. `StrategyConfig`
  carries the Upstox access token, so serialize each allowed value explicitly.
  Keep credentials, exception text, raw market candles, and user identifiers out
  of shared JSON. Keep `.status` files local. Preserve the legacy local report reader.
- Keep storage logic outside the UI. Write the local report atomically and call
  cloud persistence from the multi-day completion path. Use bounded timeouts and
  retries. Make an unsuccessful upload visible separately from strategy failure
  and keep the immediate result usable. If offering a retry, reuse the completed
  artifact and its key. A local copy can be lost before retry after a Render restart.
- List one bounded page of keys on demand, with a continuation token for **Load more**.
  Fetch and validate only the selected JSON. Add a page-level helper to the R2
  adapter if necessary. The current `list_objects()` walks the whole prefix and
  can return empty or partial results on failure. Keep its migration callers intact.
  Distinguish unavailable history from an empty page and isolate malformed reports.
  [Cloudflare R2 S3 API](https://developers.cloudflare.com/r2/api/s3/api/)
- Keep blocking R2 calls off the NiceGUI event loop. Scope new async view state to
  the requesting client, and check completion routing with two concurrent clients.
  The current UI uses a module-level completion queue and second-resolution job IDs.
  Fix collisions or cross-client delivery within the multi-day flow if reproduced.
- Use a server-side feature flag, disabled by default. With cloud history disabled,
  retain existing local behavior. With it enabled, list the cloud catalog and show
  explicit loading, empty, and retryable error states. No bucket-wide scan at startup.

## Acceptance criteria

- A completed multi-day run still displays its result and creates one durable R2 JSON
  report. Retrying a save cannot create a second report, and simultaneous runs have
  independent IDs and results.
- The same report opens from a fresh browser and after a Render restart with an empty
  local results directory. Daily and aggregate P&L match the just-completed run.
- History loads one page at a time and reads report JSON on selection. Older pages,
  malformed JSON, empty history, and R2 failures have verifiable behavior.
- An upload failure preserves the local report and displays the completed result
  with a clear cloud-save warning. Shared entries contain only allowed fields.
- Existing local reports remain readable and local data is preserved. A source-only
  deployment keeps credentials and data files out of Git. The rollback is to disable
  cloud history, with uploaded reports retained for recovery.
