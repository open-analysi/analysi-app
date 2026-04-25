"""
Unit tests for centralized Valkey connection configuration.
Tests ValkeyDBConfig.get_redis_settings() factory method.
"""

import os
from unittest.mock import patch

from arq.connections import RedisSettings

from analysi.config.valkey_db import ValkeyDBConfig


class TestGetRedisSettings:
    """Test ValkeyDBConfig.get_redis_settings() factory."""

    def test_returns_redis_settings_instance(self):
        """Factory returns an ARQ RedisSettings."""
        settings = ValkeyDBConfig.get_redis_settings(
            database=ValkeyDBConfig.ALERT_PROCESSING_DB
        )
        assert isinstance(settings, RedisSettings)

    def test_default_host_and_port(self):
        """Uses VALKEY_HOST/VALKEY_PORT env vars with sensible defaults."""
        with patch.dict(os.environ, {}, clear=False):
            # Remove any existing overrides
            env = {
                k: v
                for k, v in os.environ.items()
                if k not in ("VALKEY_HOST", "VALKEY_PORT", "REDIS_HOST", "REDIS_PORT")
            }
            with patch.dict(os.environ, env, clear=True):
                settings = ValkeyDBConfig.get_redis_settings(
                    database=ValkeyDBConfig.ALERT_PROCESSING_DB
                )
                assert settings.host == "valkey"
                assert settings.port == 6379

    def test_custom_host_and_port_from_env(self):
        """Reads host/port from VALKEY_HOST and VALKEY_PORT env vars."""
        with patch.dict(
            os.environ,
            {"VALKEY_HOST": "custom-valkey", "VALKEY_PORT": "6380"},
        ):
            settings = ValkeyDBConfig.get_redis_settings(
                database=ValkeyDBConfig.ALERT_PROCESSING_DB
            )
            assert settings.host == "custom-valkey"
            assert settings.port == 6380

    def test_database_passed_through(self):
        """Database number is passed to RedisSettings."""
        settings = ValkeyDBConfig.get_redis_settings(database=5)
        assert settings.database == 5

    def test_password_from_env(self):
        """Reads password from VALKEY_PASSWORD env var."""
        with patch.dict(os.environ, {"VALKEY_PASSWORD": "s3cret"}):
            settings = ValkeyDBConfig.get_redis_settings(
                database=ValkeyDBConfig.ALERT_PROCESSING_DB
            )
            assert settings.password == "s3cret"

    def test_no_password_when_env_not_set(self):
        """Password is None when VALKEY_PASSWORD is not set."""
        env = {k: v for k, v in os.environ.items() if k != "VALKEY_PASSWORD"}
        with patch.dict(os.environ, env, clear=True):
            settings = ValkeyDBConfig.get_redis_settings(
                database=ValkeyDBConfig.ALERT_PROCESSING_DB
            )
            assert settings.password is None

    def test_alert_processing_db(self):
        """Convenience: correct DB for alert processing."""
        settings = ValkeyDBConfig.get_redis_settings(
            database=ValkeyDBConfig.ALERT_PROCESSING_DB
        )
        assert settings.database == ValkeyDBConfig.ALERT_PROCESSING_DB

    def test_integration_worker_db(self):
        """Convenience: correct DB for integration worker."""
        settings = ValkeyDBConfig.get_redis_settings(
            database=ValkeyDBConfig.INTEGRATION_WORKER_DB
        )
        assert settings.database == ValkeyDBConfig.INTEGRATION_WORKER_DB

    def test_test_mode_overrides(self):
        """In test mode, uses localhost and test DB numbers."""
        with patch.dict(os.environ, {"PYTEST_CURRENT_TEST": "yes"}):
            settings = ValkeyDBConfig.get_redis_settings(
                database=ValkeyDBConfig.ALERT_PROCESSING_DB, test_mode=True
            )
            assert settings.host == "localhost"
            assert settings.database == ValkeyDBConfig.ALERT_PROCESSING_DB

    def test_test_mode_respects_env_overrides(self):
        """Test mode still respects explicit VALKEY_HOST override."""
        with patch.dict(
            os.environ,
            {"PYTEST_CURRENT_TEST": "yes", "VALKEY_HOST": "test-valkey"},
        ):
            settings = ValkeyDBConfig.get_redis_settings(
                database=ValkeyDBConfig.ALERT_PROCESSING_DB, test_mode=True
            )
            assert settings.host == "test-valkey"


class TestLegacyEnvCompat:
    """Test backward compatibility with REDIS_HOST/REDIS_PORT env vars."""

    def test_falls_back_to_redis_host(self):
        """Falls back to REDIS_HOST when VALKEY_HOST is not set."""
        env = {k: v for k, v in os.environ.items() if k != "VALKEY_HOST"}
        env["REDIS_HOST"] = "legacy-redis"
        with patch.dict(os.environ, env, clear=True):
            settings = ValkeyDBConfig.get_redis_settings(
                database=ValkeyDBConfig.ALERT_PROCESSING_DB
            )
            assert settings.host == "legacy-redis"

    def test_valkey_host_takes_precedence_over_redis_host(self):
        """VALKEY_HOST wins over REDIS_HOST."""
        with patch.dict(
            os.environ,
            {"VALKEY_HOST": "new-valkey", "REDIS_HOST": "old-redis"},
        ):
            settings = ValkeyDBConfig.get_redis_settings(
                database=ValkeyDBConfig.ALERT_PROCESSING_DB
            )
            assert settings.host == "new-valkey"

    def test_falls_back_to_redis_port(self):
        """Falls back to REDIS_PORT when VALKEY_PORT is not set."""
        env = {k: v for k, v in os.environ.items() if k != "VALKEY_PORT"}
        env["REDIS_PORT"] = "6381"
        with patch.dict(os.environ, env, clear=True):
            settings = ValkeyDBConfig.get_redis_settings(
                database=ValkeyDBConfig.ALERT_PROCESSING_DB
            )
            assert settings.port == 6381
