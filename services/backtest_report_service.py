"""Persistence for completed multi-day backtest reports."""

import json
import logging
import math
import os
import re
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import uuid4

from botocore.exceptions import ClientError

from models.backtest_result import BacktestResult, DayResult
from services.r2_service import create_client

logger = logging.getLogger(__name__)

REPORT_PREFIX = "backtest_results/v1/"
_LATEST_TIMESTAMP = datetime.max.replace(tzinfo=UTC)
_REPORT_KEY_PATTERN = re.compile(
    rf"{re.escape(REPORT_PREFIX)}([0-9]{{18}})_(job_[0-9]{{8}}_[0-9]{{6}}_[0-9a-f]{{32}})\.json"
)
_PAGE_SIZE = 20
_MAX_REPORT_BYTES = 2 * 1024 * 1024


class ReportUnavailable(Exception):
    """The selected object no longer exists."""


class InvalidReport(Exception):
    """The selected object could not be decoded as a v1 report."""


def cloud_history_enabled() -> bool:
    return os.getenv("BACKTEST_CLOUD_HISTORY", "").strip().lower() == "true"


def _cloud_storage():
    bucket = os.getenv("R2_BUCKET_NAME", "").strip()
    if not cloud_history_enabled() or not bucket:
        raise RuntimeError("Cloud backtest history is not configured")
    client = create_client(
        connect_timeout=3,
        read_timeout=5,
        retries={"mode": "standard", "total_max_attempts": 2},
    )
    if client is None:
        raise RuntimeError("Cloud backtest history credentials are missing")
    return bucket, client


def new_job_id() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    return f"job_{timestamp}_{uuid4().hex}"


def _day_data(day):
    return {"date": day.date, "pnl": day.pnl} if day is not None else None


def _report_key(job_id: str, completed_at: datetime) -> str:
    remaining = _LATEST_TIMESTAMP - completed_at
    reverse_seconds = remaining.days * 86400 + remaining.seconds
    reverse_microseconds = reverse_seconds * 1_000_000 + remaining.microseconds
    return f"{REPORT_PREFIX}{reverse_microseconds:018d}_{job_id}.json"


def list_report_page(continuation_token: str | None = None):
    """List one page of report keys with timestamps, without fetching any bodies."""
    bucket, client = _cloud_storage()
    request = {"Bucket": bucket, "Prefix": REPORT_PREFIX, "MaxKeys": _PAGE_SIZE}
    if continuation_token is not None:
        request["ContinuationToken"] = continuation_token
    with closing(client):
        page = client.list_objects_v2(**request)

    entries = []
    for item in page.get("Contents", []):
        key = item["Key"]
        match = _REPORT_KEY_PATTERN.fullmatch(key)
        if match:
            reverse_microseconds, job_id = match.groups()
            try:
                completed_at = _LATEST_TIMESTAMP - timedelta(microseconds=int(reverse_microseconds))
            except OverflowError:
                continue
            entries.append((key, job_id, completed_at))
    return entries, page["NextContinuationToken"] if page.get("IsTruncated") else None


def list_report_summaries(continuation_token: str | None = None):
    """Include the requested period for each entry in one bounded history page."""
    entries, next_token = list_report_page(continuation_token)

    def with_period(entry):
        key, job_id, completed_at = entry
        try:
            _, start_date, end_date = _read_report(key)
        except Exception:
            start_date = end_date = None
        return key, job_id, completed_at, start_date, end_date

    with ThreadPoolExecutor(max_workers=4) as executor:
        summaries = list(executor.map(with_period, entries))
    return summaries, next_token


def read_report(key: str) -> BacktestResult:
    return _read_report(key)[0]


def _read_report(key: str):
    """Read one v1 report and reconstruct its result from validated daily P&L."""
    match = _REPORT_KEY_PATTERN.fullmatch(key)
    if match is None:
        raise InvalidReport

    bucket, client = _cloud_storage()
    with closing(client):
        try:
            response = client.get_object(Bucket=bucket, Key=key)
        except ClientError as error:
            if error.response["Error"]["Code"] == "NoSuchKey":
                raise ReportUnavailable from error
            raise
        with closing(response["Body"]) as body:
            payload = body.read(_MAX_REPORT_BYTES + 1)

    if len(payload) > _MAX_REPORT_BYTES:
        raise InvalidReport
    try:
        report = json.loads(payload)
        job_id = report["job_id"]
        completed_at = datetime.fromisoformat(report["completed_at"])
        if (
            type(report["schema_version"]) is not int
            or report["schema_version"] != 1
            or job_id != match[2]
            or completed_at.utcoffset() != timedelta(0)
            or _report_key(job_id, completed_at) != key
        ):
            raise InvalidReport
        start_date = datetime.strptime(report["start_date"], "%Y-%m-%d").date()
        end_date = datetime.strptime(report["end_date"], "%Y-%m-%d").date()
        if start_date > end_date:
            raise InvalidReport
        raw_days = report["result"]["days"]
        if not isinstance(raw_days, list):
            raise InvalidReport
        days = []
        previous_date = None
        for day in raw_days:
            day_date = datetime.strptime(day["date"], "%Y-%m-%d").date()
            pnl = day["pnl"]
            if (
                not start_date <= day_date <= end_date
                or (previous_date is not None and day_date <= previous_date)
                or type(pnl) not in (int, float)
                or not math.isfinite(pnl)
            ):
                raise InvalidReport
            days.append(DayResult(day_date.isoformat(), pnl))
            previous_date = day_date
        result = BacktestResult(days)
        if not math.isfinite(result.total_pnl):
            raise InvalidReport
        return result, start_date.isoformat(), end_date.isoformat()
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError) as error:
        raise InvalidReport from error


def save_completed_report(
    results_dir: Path, job_id: str, result: BacktestResult, start_date: str, end_date: str
) -> bool | None:
    """Save legacy local JSON and return the cloud save outcome, or None in local mode."""
    data = {
        "total_days": result.total_days,
        "profitable_days": result.profitable_days,
        "losing_days": result.losing_days,
        "win_rate": result.win_rate,
        "total_pnl": result.total_pnl,
        "average_pnl": result.average_pnl,
        "best_day": _day_data(result.best_day),
        "worst_day": _day_data(result.worst_day),
        "days": [_day_data(day) for day in result.days],
    }
    completed_at = datetime.now(UTC)
    local_path = results_dir / f"{job_id}.json"
    with NamedTemporaryFile(dir=results_dir, mode="w", encoding="utf-8", delete=False) as file:
        temporary_path = Path(file.name)
        try:
            json.dump(data, file)
            file.close()
            temporary_path.replace(local_path)
        finally:
            temporary_path.unlink(missing_ok=True)

    if not cloud_history_enabled():
        return None

    key = _report_key(job_id, completed_at)
    report = {
        "schema_version": 1,
        "job_id": job_id,
        "completed_at": completed_at.isoformat(),
        "start_date": start_date,
        "end_date": end_date,
        "result": data,
    }
    try:
        payload = json.dumps(report, allow_nan=False).encode("utf-8")
        bucket, client = _cloud_storage()
        with closing(client):
            client.put_object(Bucket=bucket, Key=key, Body=payload, ContentType="application/json")
        return True
    except Exception:
        logger.warning("Cloud report save failed for %s", job_id)
        return False
