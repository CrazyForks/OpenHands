"""Shared Google Cloud Storage client.

This module provides a singleton GCS client to avoid connection pool exhaustion.
The default urllib3 pool size (10 connections) is easily exceeded under load when
each request creates its own storage.Client(). By sharing a single client instance,
we reuse the underlying HTTP connection pool across all requests.
"""

import threading
from functools import lru_cache

from google.cloud import storage
from google.cloud.storage.client import Client

_client_lock = threading.Lock()
_client: Client | None = None


def get_gcs_client() -> Client:
    """Get the shared GCS client instance.

    The client is created lazily on first access and reused for all subsequent
    calls. This is thread-safe and the GCS client itself is designed to be
    shared across threads.

    Returns:
        A shared google.cloud.storage.Client instance.
    """
    global _client
    if _client is not None:
        return _client

    with _client_lock:
        # Double-check after acquiring lock
        if _client is None:
            _client = storage.Client()
        return _client


@lru_cache(maxsize=128)
def get_bucket(bucket_name: str):
    """Get a bucket reference from the shared client.

    Bucket references are cached since they're lightweight objects that just
    hold the bucket name and client reference.

    Args:
        bucket_name: Name of the GCS bucket.

    Returns:
        A google.cloud.storage.Bucket instance.
    """
    return get_gcs_client().bucket(bucket_name)
