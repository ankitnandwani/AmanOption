#!/usr/bin/env python3
"""
Migration utility to upload local historical cache files to Cloudflare R2.

Features:
- Preserves current key layout (filename as object key).
- Supports dry-run mode to list actions without uploading.
- Supports resuming by skipping files that already exist in R2.
- Supports force mode to re-upload existing objects.
- Reports progress and summary.

Environment variables:
- R2_ENDPOINT: Cloudflare R2 endpoint URL (e.g., https://<account_id>.r2.cloudflarestorage.com)
- R2_ACCESS_KEY_ID: Access key ID for R2
- R2_SECRET_ACCESS_KEY: Secret access key for R2
- R2_BUCKET: Name of the R2 bucket to store the cache (required)

Usage:
    python migrate_cache_to_r2.py [--dry-run] [--force] [--bucket BUCKET_OVERRIDE]

"""

import os
import sys
from pathlib import Path

# Add the services directory to the path to import r2_service
sys.path.append(os.path.join(os.path.dirname(__file__), 'services'))
from r2_service import get_client, object_exists, put_object

# Constants
HISTORICAL_CACHE_DIR = Path("historical_cache")
DEFAULT_CACHE_DIR = HISTORICAL_CACHE_DIR

def list_cache_files(cache_dir: Path) -> list[Path]:
    """List all .pkl files in the cache directory."""
    if not cache_dir.is_dir():
        print(f"Error: Cache directory '{cache_dir}' does not exist.")
        sys.exit(1)
    files = list(cache_dir.glob("*.pkl"))
    if not files:
        print(f"Warning: No .pkl files found in '{cache_dir}'.")
    return files

def upload_file(local_path: Path, bucket: str, key: str, dry_run: bool = False) -> bool:
    """
    Upload a single file to R2.
    Returns True on success, False on failure.
    """
    if dry_run:
        print(f"[DRY-RUN] Would upload {local_path} to s3://{bucket}/{key}")
        return True

    # Read the file data
    try:
        data = local_path.read_bytes()
    except Exception as e:
        print(f"Error reading {local_path}: {e}")
        return False

    # Upload to R2
    success = put_object(bucket, key, data)
    if success:
        print(f"Uploaded: {local_path} -> s3://{bucket}/{key} ({len(data)} bytes)")
    else:
        print(f"Failed to upload: {local_path} -> s3://{bucket}/{key}")
    return success

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Migrate historical cache to R2")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform a dry run without actually uploading files",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-upload of files that already exist in R2",
    )
    parser.add_argument(
        "--bucket",
        help="Override the R2 bucket name (otherwise from R2_BUCKET environment variable)",
    )
    parser.add_argument(
        "--cache-dir",
        default=str(HISTORICAL_CACHE_DIR),
        help=f"Directory containing .pkl cache files (default: {HISTORICAL_CACHE_DIR})",
    )
    args = parser.parse_args()

    # Determine bucket name
    bucket_name = args.bucket or os.getenv("R2_BUCKET")
    if not bucket_name:
        print("Error: R2 bucket name must be provided via --bucket or R2_BUCKET environment variable.")
        sys.exit(1)

    # List cache files
    cache_dir = Path(args.cache_dir)
    files = list_cache_files(cache_dir)
    print(f"Found {len(files)} .pkl files in {cache_dir}")

    # Check for required credentials only if we are going to make R2 calls
    if not args.dry_run:
        client = get_client()
        if client is None:
            print("Error: R2 credentials not fully set. Check R2_ENDPOINT, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY.")
            sys.exit(1)

    # Process each file
    success_count = 0
    failure_count = 0
    skip_count = 0

    for local_path in files:
        key = local_path.name  # Use filename as the object key

        # Check if we should skip (if exists and not force)
        if not args.force and not args.dry_run:
            if object_exists(bucket_name, key):
                print(f"Skipping (exists in R2): {local_path} -> s3://{bucket_name}/{key}")
                skip_count += 1
                continue

        # Upload the file
        if upload_file(local_path, bucket_name, key, dry_run=args.dry_run):
            success_count += 1
        else:
            failure_count += 1

    # Summary
    print("\nMigration Summary:")
    print(f"  Total files processed: {len(files)}")
    if not args.dry_run:
        print(f"  Successfully uploaded: {success_count}")
        print(f"  Skipped (already existed): {skip_count}")
    print(f"  Failed: {failure_count}")
    if args.dry_run:
        print("  (This was a dry run; no files were actually uploaded)")

    if failure_count > 0:
        sys.exit(1)

if __name__ == "__main__":
    main()