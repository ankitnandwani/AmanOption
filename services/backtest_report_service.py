"""Persistence for completed multi-day backtest reports."""

import json
import logging
import os
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import uuid4

from models.backtest_result import BacktestResult
from services.r2_service import create_client

logger = logging.getLogger(__name__)

REPORT_PREFIX = "backtest_results/v1/"
_LATEST_TIMESTAMP = datetime.max.replace(tzinfo=UTC)


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

    if os.getenv("BACKTEST_CLOUD_HISTORY", "").strip().lower() != "true":
        return None

    bucket = os.getenv("R2_BUCKET_NAME", "").strip()
    if not bucket:
        logger.warning("Cloud backtest report bucket is missing")
        return False

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
        client = create_client(
            connect_timeout=3,
            read_timeout=5,
            retries={"mode": "standard", "total_max_attempts": 2},
        )
        if client is None:
            return False
        with closing(client):
            client.put_object(Bucket=bucket, Key=key, Body=payload, ContentType="application/json")
        return True
    except Exception:
        logger.warning("Cloud report save failed for %s", job_id)
        return False
