import json
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from botocore.awsrequest import AWSResponse
from botocore.exceptions import ClientError

from models.backtest_result import BacktestResult, DayResult
from services import backtest_report_service as reports
from services.r2_service import create_client


class TestBacktestReports(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.results_dir = Path(directory)
        self.result = BacktestResult([DayResult("2026-11-02", 770.25), DayResult("2026-11-03", 2002)])
        self.job_id = reports.new_job_id()
        self.env = self.enterContext(patch.dict(os.environ, {}, clear=True))

    def save(self):
        return reports.save_completed_report(
            self.results_dir, self.job_id, self.result, "2026-11-01", "2026-11-03"
        )

    def local_report(self):
        return json.loads((self.results_dir / f"{self.job_id}.json").read_text())

    def test_default_saves_legacy_json_without_contacting_r2(self):
        with patch.object(reports, "create_client") as factory:
            self.assertIsNone(self.save())
        factory.assert_not_called()
        self.assertEqual(self.local_report()["total_pnl"], 2772.25)
        self.assertEqual(self.local_report()["days"][0], {"date": "2026-11-02", "pnl": 770.25})
        self.assertEqual(len(list(self.results_dir.iterdir())), 1)

    def test_r2_report_contains_only_expected_fields(self):
        self.env.update(BACKTEST_CLOUD_HISTORY="true", R2_BUCKET_NAME="test-bucket")
        with patch.object(reports, "create_client") as factory:
            self.assertTrue(self.save())
        put = factory.return_value.put_object
        put.assert_called_once()
        request = put.call_args.kwargs
        self.assertEqual(request["Bucket"], "test-bucket")
        self.assertEqual(request["ContentType"], "application/json")
        report = json.loads(request["Body"])
        self.assertEqual(
            set(report), {"schema_version", "job_id", "completed_at", "start_date", "end_date", "result"}
        )
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["job_id"], self.job_id)
        self.assertEqual(report["result"], self.local_report())
        self.assertEqual((report["start_date"], report["end_date"]), ("2026-11-01", "2026-11-03"))
        completed_at = datetime.fromisoformat(report["completed_at"])
        self.assertEqual(completed_at.tzinfo, UTC)
        self.assertEqual(request["Key"], reports._report_key(self.job_id, completed_at))

    def test_sdk_retries_with_same_object_key_and_payload(self):
        self.env.update(
            BACKTEST_CLOUD_HISTORY="true",
            R2_BUCKET_NAME="test-bucket",
            R2_ENDPOINT="https://example.invalid",
            R2_ACCESS_KEY_ID="dummy",
            R2_SECRET_ACCESS_KEY="dummy",
            AWS_DEFAULT_REGION="auto",
        )
        # Stub HTTP transport while exercising the real botocore retry handler.
        unavailable = AWSResponse(
            "", 503, {}, Mock(**{"stream.return_value": [b"<Error><Code>SlowDown</Code></Error>"]})
        )
        ok = AWSResponse("", 200, {}, Mock(**{"stream.return_value": []}))
        with patch("botocore.httpsession.URLLib3Session.send", side_effect=[unavailable, ok]) as send:
            self.assertTrue(self.save())
        first, second = [call.args[0] for call in send.call_args_list]
        self.assertEqual(first.url, second.url)
        self.assertEqual(first.body, second.body)

    def test_cloud_failure_keeps_local_result(self):
        self.env.update(BACKTEST_CLOUD_HISTORY="true", R2_BUCKET_NAME="test-bucket")
        with patch.object(reports, "create_client") as factory, self.assertLogs(reports.logger):
            factory.return_value.put_object.side_effect = OSError("storage unavailable")
            self.assertIs(self.save(), False)
        self.assertEqual(self.local_report()["total_pnl"], 2772.25)

    def test_concurrent_jobs_have_unique_ids_and_keys_sort_newest_first(self):
        with ThreadPoolExecutor(max_workers=4) as executor:
            job_ids = list(executor.map(lambda _: reports.new_job_id(), range(16)))
        self.assertEqual(len(set(job_ids)), len(job_ids))
        older = reports._report_key(job_ids[0], datetime(2026, 11, 2, tzinfo=UTC))
        newer = reports._report_key(job_ids[1], datetime(2026, 11, 3, tzinfo=UTC))
        self.assertLess(newer, older)

    def test_list_returns_one_page_at_a_time_and_never_reads_report_bodies(self):
        self.env.update(BACKTEST_CLOUD_HISTORY="true", R2_BUCKET_NAME="test-bucket")
        older_time = datetime(2026, 11, 2, tzinfo=UTC)
        newer_time = datetime(2026, 11, 3, tzinfo=UTC)
        older = reports._report_key(self.job_id, older_time)
        newer = reports._report_key(self.job_id, newer_time)
        with patch.object(reports, "create_client") as factory:
            client = factory.return_value
            client.list_objects_v2.side_effect = [
                {"Contents": [{"Key": newer}, {"Key": "backtest_results/v1/other.json"}],
                 "IsTruncated": True, "NextContinuationToken": "opaque"},
                {"Contents": [{"Key": older}], "IsTruncated": False},
            ]
            entries, token = reports.list_report_page()
            self.assertEqual(entries, [(newer, self.job_id, newer_time)])
            self.assertEqual(token, "opaque")
            self.assertEqual(reports.list_report_page(token), ([(older, self.job_id, older_time)], None))
            first, second = [call.kwargs for call in client.list_objects_v2.call_args_list]
            self.assertEqual(first, {"Bucket": "test-bucket", "Prefix": reports.REPORT_PREFIX, "MaxKeys": 20})
            self.assertEqual(second, dict(first, ContinuationToken="opaque"))
            client.get_object.assert_not_called()

    def test_read_reconstructs_daily_pnl_and_rejects_invalid_reports(self):
        self.env.update(BACKTEST_CLOUD_HISTORY="true", R2_BUCKET_NAME="test-bucket")
        with patch.object(reports, "create_client") as factory:
            self.assertTrue(self.save())
            client = factory.return_value
            request = client.put_object.call_args.kwargs
            body = BytesIO(request["Body"])
            client.get_object.return_value = {"Body": body}
            self.assertEqual(reports.read_report(request["Key"]), self.result)
            self.assertTrue(body.closed)
            client.get_object.assert_called_once_with(Bucket="test-bucket", Key=request["Key"])

            report = json.loads(request["Body"])
            report["result"]["days"][0]["pnl"] = float("inf")
            for payload in (b"{", json.dumps(report).encode(), b" " * (2 * 1024 * 1024 + 1)):
                with self.subTest(size=len(payload)), self.assertRaises(reports.InvalidReport):
                    client.get_object.return_value = {"Body": BytesIO(payload)}
                    reports.read_report(request["Key"])

    def test_missing_report_is_distinct_from_storage_failure(self):
        self.env.update(BACKTEST_CLOUD_HISTORY="true", R2_BUCKET_NAME="test-bucket")
        key = reports._report_key(self.job_id, datetime(2026, 11, 3, tzinfo=UTC))
        with patch.object(reports, "create_client") as factory:
            client = factory.return_value
            client.get_object.side_effect = ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
            with self.assertRaises(reports.ReportUnavailable):
                reports.read_report(key)
            client.list_objects_v2.side_effect = OSError("storage unavailable")
            with self.assertRaises(OSError):
                reports.list_report_page()
            with self.assertRaises(reports.InvalidReport):
                reports.read_report("historical_cache/2026-11-03.pkl")
            client.get_object.assert_called_once()
