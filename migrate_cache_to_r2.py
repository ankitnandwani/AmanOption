#!/usr/bin/env python3
"""Resumable migration utility for the AmanOptions historical cache.

Uploads the local `historical_cache/*.pkl` files to a private Cloudflare R2
bucket so the deployed application can read the shared cache instead of relying
on an ephemeral local disk.

Modes
-----
``--list``     Inventory the local cache and, when credentials are available,
               compare it against the objects already present in R2.
``--dry-run``  Print the planned actions without writing anything to R2.
``--upload``   Upload missing objects (default). Resumable and retrying.
``--verify``   Verify object count, total bytes, per-object size and checksums.

Safety
------
* The local cache files are only ever read. They are never modified or deleted.
* The object key layout is taken from ``services.cache_keys`` so the objects
  written here are exactly the objects the application reads.
* Uploads are idempotent: an object that already exists with the expected size
  is skipped, and every upload is retried on transient failure.

Environment variables
---------------------
``R2_ENDPOINT``            Cloudflare R2 endpoint URL.
``R2_ACCESS_KEY_ID``       R2 access key id.
``R2_SECRET_ACCESS_KEY``   R2 secret access key.
``R2_BUCKET_NAME``         Target bucket (also accepted: ``R2_BUCKET``).

Usage
-----
    python migrate_cache_to_r2.py --list
    python migrate_cache_to_r2.py --dry-run
    python migrate_cache_to_r2.py --upload
    python migrate_cache_to_r2.py --verify
"""

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.cache_keys import CACHE_FILE_SUFFIX, R2_KEY_PREFIX, local_cache_dir
from services.r2_service import get_client, head_object, list_objects, put_file

DEFAULT_CACHE_DIR = REPO_ROOT / local_cache_dir()
DEFAULT_STATE_FILE = REPO_ROOT / "migration_state.json"
STATE_VERSION = 1

# Status values stored in the state file.
STATUS_UPLOADED = "uploaded"
STATUS_SKIPPED = "skipped"
STATUS_FAILED = "failed"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def format_bytes(size: int) -> str:
    """Format a byte count for human-readable output."""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def object_key_for(local_path: Path, key_prefix: str = R2_KEY_PREFIX) -> str:
    """Return the R2 object key for a local cache file.

    The layout matches ``services.historical_service.get_historical_candles``:
    ``historical_cache/YYYY-MM-DD.pkl``.
    """
    prefix = (key_prefix or "").strip("/")
    file_name = local_path.name
    if not prefix:
        return file_name
    return f"{prefix}/{file_name}"


def compute_checksums(path: Path) -> Tuple[str, str]:
    """Return the (md5, sha256) hex digests of a file, read in chunks."""
    md5 = hashlib.md5()
    sha256 = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            md5.update(chunk)
            sha256.update(chunk)
    return md5.hexdigest(), sha256.hexdigest()


def etag_looks_like_md5(etag: Optional[str]) -> bool:
    """Return True when an ETag is a plain MD5 digest (single-part upload)."""
    if not etag:
        return False
    candidate = etag.strip('"')
    return len(candidate) == 32 and all(c in "0123456789abcdefABCDEF" for c in candidate)


def list_cache_files(cache_dir: Path) -> List[Path]:
    """Return the cache files in ``cache_dir``, sorted by name."""
    if not cache_dir.is_dir():
        raise FileNotFoundError(f"Cache directory '{cache_dir}' does not exist.")
    return sorted(cache_dir.glob(f"*{CACHE_FILE_SUFFIX}"))


# --------------------------------------------------------------------------- #
# State file (resume support)
# --------------------------------------------------------------------------- #
class MigrationState:
    """Tracks per-file migration progress so an interrupted run can resume."""

    def __init__(self, path: Path, bucket: str, key_prefix: str):
        self.path = path
        self.bucket = bucket
        self.key_prefix = key_prefix
        self.files: Dict[str, dict] = {}
        self.load()

    def load(self) -> None:
        """Load an existing state file if present and usable."""
        if not self.path.is_file():
            return
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError) as exc:
            print(f"Warning: ignoring unreadable state file {self.path}: {exc}")
            return
        if not isinstance(data, dict):
            return
        if data.get("bucket") and data["bucket"] != self.bucket:
            print(
                f"Warning: state file {self.path} was written for bucket "
                f"'{data['bucket']}'; continuing with '{self.bucket}'."
            )
            return
        files = data.get("files")
        if isinstance(files, dict):
            self.files = files

    def get(self, key: str) -> Optional[dict]:
        """Return the recorded state for an object key."""
        record = self.files.get(key)
        return record if isinstance(record, dict) else None

    def record(self, key: str, status: str, size: int, md5: str = "", sha256: str = "", attempts: int = 0, error: str = "") -> None:
        """Record the outcome for an object key."""
        self.files[key] = {
            "status": status,
            "size": size,
            "md5": md5,
            "sha256": sha256,
            "attempts": attempts,
            "error": error,
            "updated_at": utc_now(),
        }

    def save(self) -> None:
        """Write the state file to disk."""
        payload = {
            "version": STATE_VERSION,
            "bucket": self.bucket,
            "key_prefix": self.key_prefix,
            "updated_at": utc_now(),
            "files": self.files,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)


# --------------------------------------------------------------------------- #
# R2 helpers
# --------------------------------------------------------------------------- #
def build_remote_index(bucket: str, key_prefix: str) -> Dict[str, dict]:
    """Return a mapping of object key -> object info for everything under the prefix."""
    prefix = (key_prefix or "").strip("/")
    if prefix:
        prefix = f"{prefix}/"
    objects = list_objects(bucket, prefix)
    index: Dict[str, dict] = {}
    for obj in objects:
        key = obj.get("key")
        if key:
            index[key] = obj
    return index


def upload_with_retry(
    local_path: Path,
    bucket: str,
    key: str,
    metadata: dict,
    retries: int,
    backoff_seconds: float,
    sleep_func=None,
) -> Tuple[bool, int, str]:
    """Upload a file, retrying transient failures.

    Returns ``(success, attempts, error_message)``.
    """
    if sleep_func is None:
        sleep_func = time.sleep
    attempts = 0
    error_message = ""
    while attempts <= retries:
        attempts += 1
        if put_file(bucket, key, local_path, metadata=metadata):
            return True, attempts, ""
        error_message = f"upload failed after {attempts} attempt(s)"
        if attempts <= retries:
            delay = backoff_seconds * (2 ** (attempts - 1))
            print(f"    retry {attempts}/{retries} in {delay:.1f}s: {key}")
            sleep_func(delay)
    return False, attempts, error_message


# --------------------------------------------------------------------------- #
# Modes
# --------------------------------------------------------------------------- #
def mode_list(args, files: List[Path], state: MigrationState, bucket: Optional[str]) -> int:
    """Print an inventory of the local cache and the matching R2 objects."""
    total_bytes = sum(path.stat().st_size for path in files)
    print(f"Local cache directory : {args.cache_dir}")
    print(f"Local cache files     : {len(files)}")
    print(f"Local cache bytes     : {total_bytes} ({format_bytes(total_bytes)})")

    remote_index: Dict[str, dict] = {}
    if bucket and args.client is not None:
        remote_index = build_remote_index(bucket, args.key_prefix)
        remote_bytes = sum(int(obj.get("size") or 0) for obj in remote_index.values())
        print(f"R2 bucket             : {bucket}")
        print(f"R2 objects (prefix)   : {len(remote_index)}")
        print(f"R2 bytes (prefix)     : {remote_bytes} ({format_bytes(remote_bytes)})")
    else:
        print("R2 bucket             : (not inspected - no credentials)")

    if args.verbose:
        for path in files:
            key = object_key_for(path, args.key_prefix)
            remote = remote_index.get(key)
            marker = "missing" if remote is None else f"remote={format_bytes(int(remote.get('size') or 0))}"
            print(f"  {path.name}  local={format_bytes(path.stat().st_size)}  {marker}")
    return 0


def plan_upload(
    args,
    files: List[Path],
    state: MigrationState,
    bucket: str,
    remote_index: Dict[str, dict],
) -> List[Tuple[Path, str, str]]:
    """Return the planned action per file as ``(path, key, action)``.

    ``action`` is one of ``upload``, ``skip`` or ``replace``.
    """
    plan: List[Tuple[Path, str, str]] = []
    for path in files:
        key = object_key_for(path, args.key_prefix)
        size = path.stat().st_size
        record = state.get(key)

        if args.force:
            plan.append((path, key, "upload"))
            continue

        remote = remote_index.get(key)
        if remote is not None:
            remote_size = int(remote.get("size") or 0)
            if remote_size == size:
                plan.append((path, key, "skip"))
            else:
                plan.append((path, key, "replace"))
            continue

        # Not in the R2 index. A previous run may still have recorded it, so confirm
        # directly before uploading.
        if record and record.get("status") in (STATUS_UPLOADED, STATUS_SKIPPED):
            head = head_object(bucket, key)
            if head is not None and int(head.get("size") or 0) == size:
                plan.append((path, key, "skip"))
                continue

        plan.append((path, key, "upload"))
    return plan


def mode_dry_run(args, files: List[Path], state: MigrationState, bucket: str) -> int:
    """Print the planned actions. Nothing is written to R2."""
    remote_index = build_remote_index(bucket, args.key_prefix)
    plan = plan_upload(args, files, state, bucket, remote_index)

    counts = {"upload": 0, "skip": 0, "replace": 0}
    upload_bytes = 0
    for path, _key, action in plan:
        counts[action] = counts.get(action, 0) + 1
        if action in ("upload", "replace"):
            upload_bytes += path.stat().st_size

    print(f"Bucket                : {bucket}")
    print(f"Key prefix            : {args.key_prefix}")
    print(f"Files planned         : {len(plan)}")
    print(f"  to upload           : {counts.get('upload', 0)}")
    print(f"  to replace (size)   : {counts.get('replace', 0)}")
    print(f"  to skip (present)   : {counts.get('skip', 0)}")
    print(f"Bytes to upload       : {upload_bytes} ({format_bytes(upload_bytes)})")
    print("(dry run - nothing was uploaded)")

    if args.verbose:
        for path, key, action in plan:
            print(f"  [{action}] {key}")
    return 0


def mode_upload(args, files: List[Path], state: MigrationState, bucket: str) -> int:
    """Upload missing objects, resuming a previous run where possible."""
    remote_index = build_remote_index(bucket, args.key_prefix)
    plan = plan_upload(args, files, state, bucket, remote_index)

    uploaded = 0
    skipped = 0
    replaced = 0
    failed = 0
    uploaded_bytes = 0

    print(f"Bucket                : {bucket}")
    print(f"Key prefix            : {args.key_prefix}")
    print(f"Files                 : {len(plan)}")
    print()

    for index, (path, key, action) in enumerate(plan, start=1):
        if action == "skip":
            skipped += 1
            state.record(
                key,
                STATUS_SKIPPED,
                path.stat().st_size,
                attempts=0,
            )
            print(f"[{index}/{len(plan)}] skip   {key} (already in R2)")
            continue

        size = path.stat().st_size
        md5, sha256 = compute_checksums(path)
        metadata = {
            "md5": md5,
            "sha256": sha256,
            "source-name": path.name,
            "source-size": str(size),
        }

        success, attempts, error = upload_with_retry(
            path,
            bucket,
            key,
            metadata,
            args.retries,
            args.backoff,
        )
        if success:
            uploaded += 1
            uploaded_bytes += size
            if action == "replace":
                replaced += 1
            state.record(key, STATUS_UPLOADED, size, md5, sha256, attempts)
            print(f"[{index}/{len(plan)}] upload {key} ({format_bytes(size)})")
        else:
            failed += 1
            state.record(key, STATUS_FAILED, size, md5, sha256, attempts, error)
            print(f"[{index}/{len(plan)}] FAILED {key}: {error}")

        # Persist progress after every file so an interrupted run can resume.
        state.save()

    state.save()

    print()
    print("Migration summary:")
    print(f"  Files processed     : {len(plan)}")
    print(f"  Uploaded            : {uploaded}")
    if replaced:
        print(f"  Replaced (size diff): {replaced}")
    print(f"  Skipped (present)   : {skipped}")
    print(f"  Failed              : {failed}")
    print(f"  Bytes uploaded      : {uploaded_bytes} ({format_bytes(uploaded_bytes)})")
    print(f"  State file          : {state.path}")
    print("  Local files         : untouched (never modified or deleted)")

    return 1 if failed else 0


def mode_verify(args, files: List[Path], bucket: str) -> int:
    """Verify object count, bytes, sizes and checksums between local and R2."""
    remote_index = build_remote_index(bucket, args.key_prefix)

    local_total = 0
    missing: List[str] = []
    size_mismatch: List[str] = []
    checksum_mismatch: List[str] = []
    checksum_ok = 0
    checksum_unverifiable = 0

    for path in files:
        key = object_key_for(path, args.key_prefix)
        local_size = path.stat().st_size
        local_total += local_size

        remote = remote_index.get(key)
        if remote is None:
            missing.append(key)
            continue

        remote_size = int(remote.get("size") or 0)
        if remote_size != local_size:
            size_mismatch.append(
                f"{key}: local={local_size} remote={remote_size}"
            )
            continue

        if args.no_checksum:
            continue

        head = head_object(bucket, key)
        if head is None:
            checksum_unverifiable += 1
            continue
        remote_md5 = (head.get("metadata") or {}).get("md5")
        remote_etag = head.get("etag")
        if not remote_md5 and etag_looks_like_md5(remote_etag):
            remote_md5 = remote_etag
        if not remote_md5:
            checksum_unverifiable += 1
            continue

        local_md5, _ = compute_checksums(path)
        if remote_md5.lower() != local_md5.lower():
            checksum_mismatch.append(
                f"{key}: local_md5={local_md5} remote_md5={remote_md5}"
            )
        else:
            checksum_ok += 1

    remote_total = sum(int(obj.get("size") or 0) for obj in remote_index.values())
    extra = sorted(set(remote_index) - {object_key_for(p, args.key_prefix) for p in files})

    print("Verification report")
    print(f"  Bucket                : {bucket}")
    print(f"  Key prefix            : {args.key_prefix}")
    print(f"  Local files           : {len(files)}")
    print(f"  Local bytes           : {local_total} ({format_bytes(local_total)})")
    print(f"  R2 objects            : {len(remote_index)}")
    print(f"  R2 bytes              : {remote_total} ({format_bytes(remote_total)})")
    print(f"  Count matches         : {len(files) == len(remote_index) and not extra}")
    print(f"  Bytes match           : {local_total == remote_total}")
    print(f"  Missing in R2         : {len(missing)}")
    print(f"  Size mismatches       : {len(size_mismatch)}")
    print(f"  Checksums verified    : {checksum_ok}")
    print(f"  Checksums unverifiable: {checksum_unverifiable}")
    print(f"  Checksum mismatches   : {len(checksum_mismatch)}")
    print(f"  Extra objects in R2   : {len(extra)}")

    for key in missing[:20]:
        print(f"  MISSING  {key}")
    if len(missing) > 20:
        print(f"  ... and {len(missing) - 20} more missing")
    for detail in size_mismatch[:20]:
        print(f"  SIZE     {detail}")
    for detail in checksum_mismatch[:20]:
        print(f"  CHECKSUM {detail}")

    ok = not missing and not size_mismatch and not checksum_mismatch
    print()
    print(f"Result: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def resolve_bucket(explicit: Optional[str]) -> Optional[str]:
    """Return the target bucket from the CLI flag or the environment."""
    return (
        explicit
        or os.getenv("R2_BUCKET_NAME")
        or os.getenv("R2_BUCKET")
        or None
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the command line parser."""
    parser = argparse.ArgumentParser(
        description="Migrate the AmanOptions historical cache to Cloudflare R2"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--list",
        action="store_true",
        help="Inventory the local cache and the objects present in R2",
    )
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the planned upload actions without writing to R2",
    )
    mode.add_argument(
        "--upload",
        action="store_true",
        help="Upload missing objects (default action)",
    )
    mode.add_argument(
        "--verify",
        action="store_true",
        help="Verify object count, bytes, sizes and checksums against R2",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-upload objects even when they already exist in R2",
    )
    parser.add_argument(
        "--bucket",
        help="Override the R2 bucket name (otherwise R2_BUCKET_NAME / R2_BUCKET)",
    )
    parser.add_argument(
        "--cache-dir",
        default=str(DEFAULT_CACHE_DIR),
        help=f"Directory containing the cache files (default: {DEFAULT_CACHE_DIR})",
    )
    parser.add_argument(
        "--key-prefix",
        default=R2_KEY_PREFIX,
        help=f"R2 object key prefix (default: {R2_KEY_PREFIX})",
    )
    parser.add_argument(
        "--state-file",
        default=str(DEFAULT_STATE_FILE),
        help=f"Progress/state file used to resume (default: {DEFAULT_STATE_FILE})",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="Number of retries per failed upload (default: 3)",
    )
    parser.add_argument(
        "--backoff",
        type=float,
        default=2.0,
        help="Base seconds for exponential backoff between retries (default: 2.0)",
    )
    parser.add_argument(
        "--no-checksum",
        action="store_true",
        help="Skip checksum verification in --verify mode",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print one line per file",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Entry point. Returns the process exit code."""
    args = build_parser().parse_args(argv)
    args.cache_dir = Path(args.cache_dir).expanduser()
    args.key_prefix = (args.key_prefix or "").strip("/")
    args.state_file = Path(args.state_file).expanduser()

    try:
        files = list_cache_files(args.cache_dir)
    except FileNotFoundError as exc:
        print(f"Error: {exc}")
        return 1

    if not files:
        print(f"Warning: no '{CACHE_FILE_SUFFIX}' files found in {args.cache_dir}.")

    bucket = resolve_bucket(args.bucket)
    args.client = get_client()

    needs_r2 = args.dry_run or args.upload or args.verify
    if needs_r2:
        if not bucket:
            print(
                "Error: target bucket not set. Pass --bucket or set R2_BUCKET_NAME "
                "(R2_BUCKET is also accepted)."
            )
            return 1
        if args.client is None:
            print(
                "Error: R2 credentials are not fully set. Check R2_ENDPOINT, "
                "R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY."
            )
            return 1

    state = MigrationState(args.state_file, bucket or "", args.key_prefix)

    if args.list:
        return mode_list(args, files, state, bucket)
    if args.dry_run:
        return mode_dry_run(args, files, state, bucket)
    if args.verify:
        return mode_verify(args, files, bucket)
    return mode_upload(args, files, state, bucket)


if __name__ == "__main__":
    sys.exit(main())
