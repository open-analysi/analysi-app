"""
Tests for centralized ObjectStorageConfig.

Validates the single source of truth for S3-compatible object storage
(MinIO in dev, any S3-compatible in production).
"""

from unittest.mock import patch

import pytest

from analysi.config.object_storage import ObjectStorageConfig


class TestObjectStorageConfig:
    """Test ObjectStorageConfig centralized configuration."""

    @pytest.mark.unit
    def test_loads_all_env_vars_from_environment(self):
        """All four core env vars are read and returned."""
        env = {
            "MINIO_ENDPOINT": "minio.prod:9000",
            "MINIO_ACCESS_KEY": "prod-key",
            "MINIO_SECRET_KEY": "prod-secret",
            "MINIO_BUCKET": "prod-bucket",
            "ARTIFACTS_BUCKET": "prod-artifacts",
        }
        with patch.dict("os.environ", env, clear=True):
            config = ObjectStorageConfig.get_settings()

        assert config["endpoint"] == "minio.prod:9000"
        assert config["access_key"] == "prod-key"
        assert config["secret_key"] == "prod-secret"
        assert config["bucket"] == "prod-bucket"
        assert config["artifacts_bucket"] == "prod-artifacts"

    @pytest.mark.unit
    def test_test_mode_endpoint_defaults_to_localhost(self):
        """test_mode=True uses localhost, not the Docker service name."""
        with patch.dict("os.environ", {}, clear=True):
            config = ObjectStorageConfig.get_settings(test_mode=True)

        assert "localhost" in config["endpoint"]

    @pytest.mark.unit
    def test_docker_mode_endpoint_defaults_to_service_name(self):
        """Default (non-test) mode uses Docker service name."""
        with patch.dict("os.environ", {}, clear=True):
            config = ObjectStorageConfig.get_settings(test_mode=False)

        assert "minio" in config["endpoint"]

    @pytest.mark.unit
    def test_endpoint_preserves_http_prefix(self):
        """If MINIO_ENDPOINT already has http://, don't double it."""
        env = {"MINIO_ENDPOINT": "http://my-minio:9000"}
        with patch.dict("os.environ", env, clear=True):
            config = ObjectStorageConfig.get_settings()

        assert config["endpoint"] == "http://my-minio:9000"
        assert "http://http://" not in config["endpoint"]

    @pytest.mark.unit
    def test_endpoint_adds_http_prefix_when_missing(self):
        """If MINIO_ENDPOINT has no protocol, we DON'T add it (consumer adds it)."""
        env = {"MINIO_ENDPOINT": "my-minio:9000"}
        with patch.dict("os.environ", env, clear=True):
            config = ObjectStorageConfig.get_settings()

        # Config returns raw value; consumers (storage.py) add http:// prefix
        assert config["endpoint"] == "my-minio:9000"

    @pytest.mark.unit
    def test_no_hardcoded_minioadmin_defaults(self):
        """access_key and secret_key must NOT default to 'minioadmin'."""
        with patch.dict("os.environ", {}, clear=True):
            config = ObjectStorageConfig.get_settings()

        assert config["access_key"] != "minioadmin"
        assert config["secret_key"] != "minioadmin"

    @pytest.mark.unit
    def test_credentials_from_env_are_used(self):
        """Env var values are propagated correctly."""
        env = {
            "MINIO_ACCESS_KEY": "my-access",
            "MINIO_SECRET_KEY": "my-secret",
        }
        with patch.dict("os.environ", env, clear=True):
            config = ObjectStorageConfig.get_settings()

        assert config["access_key"] == "my-access"
        assert config["secret_key"] == "my-secret"

    @pytest.mark.unit
    def test_validate_rejects_empty_access_key(self):
        """Validation catches empty access_key."""
        config = {
            "endpoint": "localhost:9000",
            "access_key": "",
            "secret_key": "ok",
            "bucket": "b",
            "artifacts_bucket": "b",
        }
        with pytest.raises(ValueError, match="access_key"):
            ObjectStorageConfig.validate(config)

    @pytest.mark.unit
    def test_validate_rejects_empty_secret_key(self):
        """Validation catches empty secret_key."""
        config = {
            "endpoint": "localhost:9000",
            "access_key": "ok",
            "secret_key": "",
            "bucket": "b",
            "artifacts_bucket": "b",
        }
        with pytest.raises(ValueError, match="secret_key"):
            ObjectStorageConfig.validate(config)

    @pytest.mark.unit
    def test_validate_accepts_complete_config(self):
        """Validation passes for complete config (no exception)."""
        config = {
            "endpoint": "localhost:9000",
            "access_key": "key",
            "secret_key": "secret",
            "bucket": "my-bucket",
            "artifacts_bucket": "my-artifacts",
        }
        # Should not raise
        ObjectStorageConfig.validate(config)

    @pytest.mark.unit
    def test_artifacts_bucket_uses_dedicated_env_var(self):
        """ARTIFACTS_BUCKET env var takes priority."""
        env = {
            "MINIO_BUCKET": "general",
            "ARTIFACTS_BUCKET": "dedicated-artifacts",
        }
        with patch.dict("os.environ", env, clear=True):
            config = ObjectStorageConfig.get_settings()

        assert config["artifacts_bucket"] == "dedicated-artifacts"

    @pytest.mark.unit
    def test_artifacts_bucket_falls_back_to_minio_bucket(self):
        """Without ARTIFACTS_BUCKET, falls back to MINIO_BUCKET."""
        env = {"MINIO_BUCKET": "general-bucket"}
        with patch.dict("os.environ", env, clear=True):
            config = ObjectStorageConfig.get_settings()

        assert config["artifacts_bucket"] == "general-bucket"

    @pytest.mark.unit
    def test_bucket_default_value(self):
        """Default bucket name when no env vars are set."""
        with patch.dict("os.environ", {}, clear=True):
            config = ObjectStorageConfig.get_settings()

        assert config["bucket"] == "analysi-storage"

    @pytest.mark.unit
    def test_credentials_are_none_when_unset(self):
        """Credentials return None when env vars unset (matches Valkey pattern)."""
        with patch.dict("os.environ", {}, clear=True):
            config = ObjectStorageConfig.get_settings()

        assert config["access_key"] is None
        assert config["secret_key"] is None
