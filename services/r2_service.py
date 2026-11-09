import os
import logging
from pathlib import Path
from typing import List, Optional

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# Singleton client
_s3_client = None


def _build_client_config() -> Config:
    """Build the botocore configuration used for the R2 client.

    Recent botocore versions attach a CRC32 checksum to every PutObject request by
    default. Cloudflare R2 does not reliably accept that parameter, and the
    checksum is not needed for correctness here, so it is only sent when a request
    genuinely requires it.
    """
    try:
        return Config(request_checksum_calculation="when_required")
    except TypeError:  # pragma: no cover - older botocore without the option
        return Config()


def get_client():
    global _s3_client
    if _s3_client is None:
        endpoint_url = os.getenv("R2_ENDPOINT")
        access_key_id = os.getenv("R2_ACCESS_KEY_ID")
        secret_access_key = os.getenv("R2_SECRET_ACCESS_KEY")
        if not endpoint_url or not access_key_id or not secret_access_key:
            logger.warning(
                "R2 credentials not fully set; R2 service will be disabled"
            )
            return None
        _s3_client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            config=_build_client_config(),
        )
    return _s3_client


def object_exists(bucket_name: str, key: str) -> bool:
    """Return True if the object exists in R2."""
    client = get_client()
    if client is None:
        return False
    try:
        client.head_object(Bucket=bucket_name, Key=key)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "404":
            return False
        # Other errors (e.g., permission) we treat as not exist to be safe
        logger.error(
            "Error checking existence of R2 object %s/%s: %s",
            bucket_name,
            key,
            e,
        )
        return False
    except Exception as e:
        logger.error(
            "Unexpected error checking existence of R2 object %s/%s: %s",
            bucket_name,
            key,
            e,
        )
        return False


def get_object(bucket_name: str, key: str) -> Optional[bytes]:
    """Fetch the object bytes from R2, or None if not found/error."""
    client = get_client()
    if client is None:
        return None
    try:
        response = client.get_object(Bucket=bucket_name, Key=key)
        body = response["Body"].read()
        return body
    except ClientError as e:
        if e.response["Error"]["Code"] == "404":
            return None
        logger.error(
            "Error fetching R2 object %s/%s: %s", bucket_name, key, e
        )
        return None
    except Exception as e:
        logger.error(
            "Unexpected error fetching R2 object %s/%s: %s",
            bucket_name,
            key,
            e,
        )
        return None


def put_object(
    bucket_name: str,
    key: str,
    data: bytes,
    metadata: Optional[dict] = None,
) -> bool:
    """Put the object data to R2. Return True on success.

    ``metadata`` is optional user metadata attached to the object (for example
    checksums recorded by the migration utility). It is omitted entirely when
    not supplied so existing call sites keep their current behaviour.
    """
    client = get_client()
    if client is None:
        return False
    try:
        kwargs = {"Bucket": bucket_name, "Key": key, "Body": data}
        if metadata:
            kwargs["Metadata"] = metadata
        client.put_object(**kwargs)
        return True
    except ClientError as e:
        logger.error(
            "Error putting R2 object %s/%s: %s", bucket_name, key, e
        )
        return False
    except Exception as e:
        logger.error(
            "Unexpected error putting R2 object %s/%s: %s",
            bucket_name,
            key,
            e,
        )
        return False


def put_file(
    bucket_name: str,
    key: str,
    file_path,
    metadata: Optional[dict] = None,
) -> bool:
    """Upload a local file to R2. Return True on success.

    Uses the managed transfer API so large files are streamed instead of being
    buffered in memory. Falls back to a buffered upload when the client does not
    expose the managed transfer helpers.
    """
    client = get_client()
    if client is None:
        return False
    path = Path(file_path)
    try:
        uploader = getattr(client, "upload_file", None)
        if callable(uploader):
            extra_args = {"Metadata": metadata} if metadata else None
            if extra_args:
                uploader(str(path), bucket_name, key, ExtraArgs=extra_args)
            else:
                uploader(str(path), bucket_name, key)
            return True
        with open(path, "rb") as handle:
            data = handle.read()
        return put_object(bucket_name, key, data, metadata=metadata)
    except ClientError as e:
        logger.error(
            "Error uploading R2 object %s/%s from %s: %s",
            bucket_name,
            key,
            path,
            e,
        )
        return False
    except Exception as e:
        logger.error(
            "Unexpected error uploading R2 object %s/%s from %s: %s",
            bucket_name,
            key,
            path,
            e,
        )
        return False


def head_object(bucket_name: str, key: str) -> Optional[dict]:
    """Return object metadata for a key in R2, or None when it is not found.

    The returned dict contains ``size``, ``etag``, ``metadata`` and
    ``last_modified``. Errors other than a missing object are logged and also
    reported as None, so callers must treat None as "unknown or missing".
    """
    client = get_client()
    if client is None:
        return None
    try:
        response = client.head_object(Bucket=bucket_name, Key=key)
        return {
            "size": response.get("ContentLength"),
            "etag": (response.get("ETag") or "").strip('"'),
            "metadata": response.get("Metadata") or {},
            "last_modified": response.get("LastModified"),
        }
    except ClientError as e:
        if e.response["Error"]["Code"] == "404":
            return None
        logger.error(
            "Error fetching R2 object metadata %s/%s: %s",
            bucket_name,
            key,
            e,
        )
        return None
    except Exception as e:
        logger.error(
            "Unexpected error fetching R2 object metadata %s/%s: %s",
            bucket_name,
            key,
            e,
        )
        return None


def list_objects(bucket_name: str, prefix: str = "") -> List[dict]:
    """List objects under a prefix in R2.

    Returns a list of dicts with ``key``, ``size``, ``etag`` and
    ``last_modified``. Pagination is handled internally. An empty list is
    returned when the client is unavailable or the listing fails.
    """
    client = get_client()
    if client is None:
        return []
    results: List[dict] = []
    continuation_token = None
    try:
        while True:
            kwargs = {"Bucket": bucket_name, "Prefix": prefix}
            if continuation_token:
                kwargs["ContinuationToken"] = continuation_token
            response = client.list_objects_v2(**kwargs)
            for item in response.get("Contents") or []:
                results.append(
                    {
                        "key": item.get("Key"),
                        "size": item.get("Size", 0),
                        "etag": (item.get("ETag") or "").strip('"'),
                        "last_modified": item.get("LastModified"),
                    }
                )
            if not response.get("IsTruncated"):
                break
            continuation_token = response.get("NextContinuationToken")
            if not continuation_token:
                break
        return results
    except ClientError as e:
        logger.error(
            "Error listing R2 objects in %s with prefix %s: %s",
            bucket_name,
            prefix,
            e,
        )
        return results
    except Exception as e:
        logger.error(
            "Unexpected error listing R2 objects in %s with prefix %s: %s",
            bucket_name,
            prefix,
            e,
        )
        return results
