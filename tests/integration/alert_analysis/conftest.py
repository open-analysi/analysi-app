"""
Fixtures for alert analysis integration tests.
"""

from collections.abc import AsyncGenerator

import pytest_asyncio
import redis.asyncio as redis
from arq import create_pool

from analysi.config.valkey_db import ValkeyDBConfig


def _test_redis_settings():
    """Single source of truth for test Valkey connection settings."""
    return ValkeyDBConfig.get_redis_settings(
        database=ValkeyDBConfig.TEST_ALERT_PROCESSING_DB,
        test_mode=True,
    )


@pytest_asyncio.fixture
async def valkey_cleanup() -> AsyncGenerator[None]:
    """
    Cleanup fixture for Valkey/Redis.
    Clears all keys in the test database before and after tests.
    """
    settings = _test_redis_settings()

    # Build URL with optional password
    password_part = f":{settings.password}@" if settings.password else ""
    url = f"redis://{password_part}{settings.host}:{settings.port}/{settings.database}"

    client = await redis.from_url(url)

    try:
        # Clean before test
        await client.flushdb()

        yield

        # Clean after test
        await client.flushdb()
    finally:
        await client.aclose()


@pytest_asyncio.fixture
async def arq_pool(valkey_cleanup):
    """
    Provides an ARQ pool connected to test Valkey instance.
    Ensures cleanup before and after test.
    """
    pool = await create_pool(_test_redis_settings())

    try:
        yield pool
    finally:
        await pool.aclose()
