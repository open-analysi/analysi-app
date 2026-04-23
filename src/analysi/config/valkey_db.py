"""Centralized Valkey/Redis database allocation and connection configuration.

This module defines the database allocation strategy for all services
and provides a single factory for ARQ RedisSettings instances.

Production/Development: DB 0-99
Testing: DB 100+

Environment variables (checked in order):
  VALKEY_HOST / REDIS_HOST  — Valkey hostname (default: valkey)
  VALKEY_PORT / REDIS_PORT  — Valkey port (default: 6379)
  VALKEY_PASSWORD           — Valkey requirepass password (default: None)
"""

import os

from arq.connections import RedisSettings


class ValkeyDBConfig:
    """Centralized Valkey database allocation configuration.

    Database Allocation:
    - 0-99: Production/Development databases
    - 100+: Testing databases
    """

    # Production/Development DBs (0-99)
    ALERT_PROCESSING_DB = int(os.getenv("VALKEY_ALERT_PROCESSING_DB", 0))
    DATA_INGESTION_DB = int(os.getenv("VALKEY_DATA_INGESTION_DB", 1))
    AUTOMATION_DB = int(os.getenv("VALKEY_AUTOMATION_DB", 2))
    SCHEDULING_DB = int(os.getenv("VALKEY_SCHEDULING_DB", 3))
    CACHE_DB = int(os.getenv("VALKEY_CACHE_DB", 4))
    INTEGRATION_WORKER_DB = int(os.getenv("VALKEY_INTEGRATION_WORKER_DB", 5))

    # Test DBs (100+)
    TEST_ALERT_PROCESSING_DB = int(os.getenv("VALKEY_TEST_ALERT_PROCESSING_DB", 100))
    TEST_DATA_INGESTION_DB = int(os.getenv("VALKEY_TEST_DATA_INGESTION_DB", 101))
    TEST_AUTOMATION_DB = int(os.getenv("VALKEY_TEST_AUTOMATION_DB", 102))
    TEST_SCHEDULING_DB = int(os.getenv("VALKEY_TEST_SCHEDULING_DB", 103))
    TEST_CACHE_DB = int(os.getenv("VALKEY_TEST_CACHE_DB", 104))
    TEST_INTEGRATION_WORKER_DB = int(
        os.getenv("VALKEY_TEST_INTEGRATION_WORKER_DB", 105)
    )
    TEST_ISOLATED_DB = int(os.getenv("VALKEY_TEST_ISOLATED_DB", 110))

    @classmethod
    def is_test_db(cls, db_num: int) -> bool:
        """Check if a database number is for testing.

        Args:
            db_num: Database number to check

        Returns:
            True if database is for testing (>= 100), False otherwise
        """
        return db_num >= 100

    @classmethod
    def get_db_name(cls, db_num: int) -> str:
        """Get human-readable name for a database number.

        Args:
            db_num: Database number

        Returns:
            Human-readable database name
        """
        db_map = {
            cls.ALERT_PROCESSING_DB: "Alert Processing",
            cls.DATA_INGESTION_DB: "Data Ingestion",
            cls.AUTOMATION_DB: "Automation",
            cls.SCHEDULING_DB: "Scheduling",
            cls.CACHE_DB: "Cache",
            cls.INTEGRATION_WORKER_DB: "Integration Worker",
            cls.TEST_ALERT_PROCESSING_DB: "Test Alert Processing",
            cls.TEST_DATA_INGESTION_DB: "Test Data Ingestion",
            cls.TEST_AUTOMATION_DB: "Test Automation",
            cls.TEST_SCHEDULING_DB: "Test Scheduling",
            cls.TEST_CACHE_DB: "Test Cache",
            cls.TEST_INTEGRATION_WORKER_DB: "Test Integration Worker",
            cls.TEST_ISOLATED_DB: "Test Isolated",
        }
        return db_map.get(db_num, f"Unknown DB {db_num}")

    @classmethod
    def get_redis_settings(
        cls, database: int, *, test_mode: bool = False
    ) -> RedisSettings:
        """Create ARQ RedisSettings for the given database number.

        Single source of truth for all Valkey connections. Reads:
          VALKEY_HOST (fallback: REDIS_HOST, default: valkey)
          VALKEY_PORT (fallback: REDIS_PORT, default: 6379)
          VALKEY_PASSWORD (default: None)

        Args:
            database: Valkey database number (use class constants).
            test_mode: If True and no VALKEY_HOST is set, defaults to localhost.
        """
        default_host = "localhost" if test_mode else "valkey"
        host = os.getenv("VALKEY_HOST") or os.getenv("REDIS_HOST") or default_host
        port = int(os.getenv("VALKEY_PORT") or os.getenv("REDIS_PORT") or 6379)
        password = os.getenv("VALKEY_PASSWORD") or None

        return RedisSettings(
            host=host,
            port=port,
            database=database,
            password=password,
        )
