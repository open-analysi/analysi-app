"""Centralized S3-compatible object storage configuration.

Single source of truth for all object storage connections (MinIO in dev,
any S3-compatible backend in production).

Environment variables:
  MINIO_ENDPOINT     — S3 endpoint (default: minio:9000)
  MINIO_ACCESS_KEY   — Access key (default: None — must be set)
  MINIO_SECRET_KEY   — Secret key (default: None — must be set)
  MINIO_BUCKET       — General-purpose bucket (default: analysi-storage)
  ARTIFACTS_BUCKET   — Artifacts bucket, falls back to MINIO_BUCKET
"""

import os


class ObjectStorageConfig:
    """Centralized object storage configuration.

    Follows the same pattern as ValkeyDBConfig in config/valkey_db.py.
    """

    @classmethod
    def get_settings(cls, *, test_mode: bool = False) -> dict[str, str | None]:
        """Load object storage settings from environment.

        Args:
            test_mode: If True and no MINIO_ENDPOINT is set, defaults to localhost:9000.
                       Otherwise defaults to the Docker service name.
        """
        default_endpoint = "localhost:9000" if test_mode else "minio:9000"
        endpoint = os.getenv("MINIO_ENDPOINT") or default_endpoint

        access_key = os.getenv("MINIO_ACCESS_KEY") or None
        secret_key = os.getenv("MINIO_SECRET_KEY") or None

        bucket = os.getenv("MINIO_BUCKET") or "analysi-storage"
        artifacts_bucket = os.getenv("ARTIFACTS_BUCKET") or bucket

        return {
            "endpoint": endpoint,
            "access_key": access_key,
            "secret_key": secret_key,
            "bucket": bucket,
            "artifacts_bucket": artifacts_bucket,
        }

    @classmethod
    def validate(cls, config: dict[str, str | None]) -> None:
        """Validate that required fields are present and non-empty.

        Raises:
            ValueError: If any required field is missing or empty.
        """
        required = ["endpoint", "access_key", "secret_key", "bucket"]
        missing = [k for k in required if not config.get(k)]
        if missing:
            raise ValueError(
                f"Object storage configuration incomplete. Missing: {missing}"
            )
