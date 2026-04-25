"""
Test configuration for different database backends.

Ephemeral test databases: Each git branch gets a unique test database name
derived from the branch name, eliminating collisions between parallel test
runs in different worktrees. The database persists between runs on the same
branch for speed; use ``make test-db-clean`` to drop all ephemeral DBs.
"""

import os
import re
import subprocess


def _get_branch_slug() -> str:
    """Derive a stable, unique slug from the current git branch.

    Returns a sanitized branch name suitable for use in a database name.
    Falls back to a random hex string for detached HEAD (e.g., in CI).
    """
    try:
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        if branch == "HEAD":
            # Detached HEAD — use short commit hash
            branch = subprocess.check_output(
                ["git", "rev-parse", "--short=8", "HEAD"],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Not in a git repo or git not available
        from uuid import uuid4

        branch = uuid4().hex[:8]

    # Sanitize: lowercase, replace non-alphanum with underscore, truncate
    slug = re.sub(r"[^a-z0-9]", "_", branch.lower())
    # Collapse multiple underscores
    slug = re.sub(r"_+", "_", slug).strip("_")
    # Postgres max identifier = 63 chars; prefix is ~16 chars
    return slug[:40]


def _get_test_db_name() -> str:
    """Build ephemeral test database name.

    If TEST_DB_NAME is set explicitly in the environment, use it as-is
    (for backwards compat / CI override). Otherwise, derive from branch.
    """
    explicit = os.environ.get("TEST_DB_NAME")
    if explicit:
        return explicit
    return f"analysi_test_{_get_branch_slug()}"


class TestConfig:
    """Configuration for test databases - PostgreSQL only."""

    # PostgreSQL configuration (for all tests)
    POSTGRES_TEST_HOST = os.getenv("TEST_DB_HOST", "localhost")
    POSTGRES_TEST_PORT = os.getenv("TEST_DB_PORT", "5432")
    POSTGRES_TEST_USER = os.getenv("TEST_DB_USER", "postgres")
    POSTGRES_TEST_PASSWORD = os.getenv("TEST_DB_PASSWORD", "postgres")
    POSTGRES_TEST_DATABASE = _get_test_db_name()

    @classmethod
    def get_postgres_test_url(cls) -> str:
        """Get PostgreSQL test database URL (async driver)."""
        return (
            f"postgresql+asyncpg://{cls.POSTGRES_TEST_USER}:{cls.POSTGRES_TEST_PASSWORD}"
            f"@{cls.POSTGRES_TEST_HOST}:{cls.POSTGRES_TEST_PORT}/{cls.POSTGRES_TEST_DATABASE}"
        )

    @classmethod
    def get_admin_database_url(cls) -> str:
        """Get URL to the ``postgres`` admin database for DDL operations.

        Uses the sync psycopg2 driver because CREATE DATABASE cannot run
        inside a transaction block (asyncpg always uses transactions).
        """
        return (
            f"postgresql+psycopg2://{cls.POSTGRES_TEST_USER}:{cls.POSTGRES_TEST_PASSWORD}"
            f"@{cls.POSTGRES_TEST_HOST}:{cls.POSTGRES_TEST_PORT}/postgres"
        )

    @classmethod
    def get_test_database_url(cls) -> str:
        """Get test database URL - always PostgreSQL."""
        return cls.get_postgres_test_url()


class IntegrationTestConfig:
    """Configuration specifically for integration tests."""

    @classmethod
    def get_database_url(cls) -> str:
        """Get database URL for integration tests (always PostgreSQL)."""
        return TestConfig.get_postgres_test_url()

    @classmethod
    def is_available(cls) -> bool:
        """Check if integration test database is available."""
        postgres_env_vars = [
            "TEST_DB_HOST",
            "TEST_DB_USER",
            "TEST_DB_PASSWORD",
        ]
        return all(os.getenv(var) is not None for var in postgres_env_vars)
