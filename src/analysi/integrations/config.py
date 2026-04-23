"""Configuration for integrations."""

import os

from arq.connections import RedisSettings

from analysi.config.valkey_db import ValkeyDBConfig


class IntegrationConfig:
    """Configuration for all integration operations."""

    # Redis/Valkey configuration — DB number only; host/port/password from ValkeyDBConfig
    REDIS_DB = int(
        os.getenv("INTEGRATION_REDIS_DB", ValkeyDBConfig.INTEGRATION_WORKER_DB)
    )

    # Worker configuration
    MAX_JOBS = int(os.getenv("INTEGRATION_MAX_JOBS", 20))
    JOB_TIMEOUT = int(os.getenv("INTEGRATION_JOB_TIMEOUT", 300))

    # Queue configuration
    BASE_QUEUE_NAME = "integrations"

    # API configuration
    BACKEND_API_HOST = os.getenv("BACKEND_API_HOST", "api")
    BACKEND_API_PORT = int(os.getenv("BACKEND_API_PORT", 8000))
    API_BASE_URL = f"http://{BACKEND_API_HOST}:{BACKEND_API_PORT}"
    # System API key sent as X-API-Key header to authenticate workers against the REST API.
    # Reads ANALYSI_SYSTEM_API_KEY; falls back to legacy BACKEND_API_AUTH_TOKEN for compatibility.
    API_AUTH_TOKEN = os.getenv("ANALYSI_SYSTEM_API_KEY") or os.getenv(
        "BACKEND_API_AUTH_TOKEN"
    )

    # Default tenant
    DEFAULT_TENANT = os.getenv("INTEGRATION_DEFAULT_TENANT", "default")

    # Reconciliation settings
    RECONCILE_INTERVAL = int(
        os.getenv("INTEGRATION_RECONCILE_INTERVAL", 300)
    )  # 5 minutes
    RECONCILE_LOCK_TTL = int(os.getenv("INTEGRATION_RECONCILE_LOCK_TTL", 30))

    # Connector settings
    POLL_INTERVAL_SECONDS = int(os.getenv("INTEGRATION_POLL_INTERVAL", 60))
    PULL_LOOKBACK_SECONDS = int(os.getenv("INTEGRATION_PULL_LOOKBACK", 120))

    # Splunk defaults (can be overridden by credentials)
    SPLUNK_HOST = os.getenv("SPLUNK_HOST", "splunk")
    SPLUNK_PORT = int(os.getenv("SPLUNK_PORT", 8089))
    SPLUNK_USERNAME = os.getenv("SPLUNK_USERNAME", "admin")
    SPLUNK_PASSWORD = os.getenv("SPLUNK_PASSWORD", "changeme123")
    SPLUNK_SEARCH_QUERY = os.getenv(
        "SPLUNK_SEARCH_QUERY", "search index=notable | head 50"
    )

    @classmethod
    def get_redis_settings(cls) -> RedisSettings:
        """Get Redis settings for ARQ."""
        return ValkeyDBConfig.get_redis_settings(database=cls.REDIS_DB)

    @classmethod
    def get_queue_name(cls, tenant_id: str = None) -> str:
        """Get tenant-aware queue name."""
        if tenant_id is None:
            tenant_id = cls.DEFAULT_TENANT
        return f"{cls.BASE_QUEUE_NAME}:tenant:{tenant_id}:queue"

    @classmethod
    def get_lock_key(cls, tenant_id: str, integration_id: str = None) -> str:
        """Get lock key for distributed locking."""
        if integration_id:
            return f"{cls.BASE_QUEUE_NAME}:lock:reconcile:{tenant_id}:{integration_id}"
        return f"{cls.BASE_QUEUE_NAME}:lock:reconcile:{tenant_id}:all"
