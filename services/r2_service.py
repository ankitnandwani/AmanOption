import os
import logging
from typing import Optional

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# Singleton client
_s3_client = None


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


def put_object(bucket_name: str, key: str, data: bytes) -> bool:
    """Put the object data to R2. Return True on success."""
    client = get_client()
    if client is None:
        return False
    try:
        client.put_object(Bucket=bucket_name, Key=key, Body=data)
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