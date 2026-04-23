"""
Pytest configuration and fixtures for Analysi tests.

Ephemeral test databases
------------------------
Each git branch gets its own PostgreSQL database (e.g.,
``analysi_test_feature_model_cleanup``). The database is created
automatically at session start via the ``ephemeral_test_db`` fixture
and persists between runs for fast re-runs. Pass ``--drop-test-db``
to drop it after the session, or use ``make test-db-clean`` to drop
all ephemeral databases.
"""

# Load test environment variables FIRST, before any other imports
from pathlib import Path

from dotenv import load_dotenv

test_env_path = Path(__file__).parent.parent / ".env.test"
if test_env_path.exists():
    load_dotenv(test_env_path)

# Branch-specific overrides (written by `make test-db-up`, gitignored).
# Loaded AFTER .env.test so it overrides defaults with per-branch values.
test_env_local_path = Path(__file__).parent.parent / ".env.test.local"
_has_test_env_local = test_env_local_path.exists()
if _has_test_env_local:
    load_dotenv(test_env_local_path, override=True)

# Now import everything else
import asyncio  # noqa: E402
import logging  # noqa: E402
from collections.abc import AsyncGenerator  # noqa: E402
from uuid import uuid4  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from analysi.db.base import Base  # noqa: E402
from analysi.models.alert import Disposition  # noqa: E402
from analysi.models.workflow import NodeTemplate  # noqa: E402
from tests.test_config import IntegrationTestConfig, TestConfig  # noqa: E402

_conftest_logger = logging.getLogger("tests.conftest")


# ---------------------------------------------------------------------------
# Pytest CLI options
# ---------------------------------------------------------------------------


def pytest_addoption(parser):
    """Register custom CLI options."""
    parser.addoption(
        "--drop-test-db",
        action="store_true",
        default=False,
        help="Drop the ephemeral test database after the session completes.",
    )


# ---------------------------------------------------------------------------
# Auto-skip tests that need infrastructure not currently available
# ---------------------------------------------------------------------------


def _is_api_reachable() -> bool:
    """Check if the backend API server is reachable (cached per session)."""
    import os
    import socket

    host = os.getenv("BACKEND_API_HOST", "localhost")
    port = int(os.getenv("BACKEND_API_PORT", "8001"))
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except (OSError, ConnectionRefusedError):
        return False


# Cache the result so we only probe once per test session
_full_stack_available: bool | None = None


def pytest_collection_modifyitems(config, items):
    """Auto-skip tests marked requires_full_stack when the API is not running."""
    global _full_stack_available

    if _full_stack_available is None:
        _full_stack_available = _is_api_reachable()

    if _full_stack_available:
        return  # full stack is up, nothing to skip

    skip_marker = pytest.mark.skip(
        reason="requires_full_stack: API server not reachable"
    )
    for item in items:
        if item.get_closest_marker("requires_full_stack"):
            item.add_marker(skip_marker)


# ---------------------------------------------------------------------------
# Ephemeral test database — session-scoped, created once per pytest run
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def ephemeral_test_db(request):
    """Create an ephemeral test database for this branch if it doesn't exist.

    Uses the sync psycopg2 driver because CREATE DATABASE cannot run
    inside a transaction block. The database name is derived from the
    current git branch (see ``tests.test_config._get_branch_slug``).

    The database persists between runs on the same branch for speed.
    Pass ``--drop-test-db`` to drop it after the session.

    Gracefully skips if PostgreSQL is not reachable (unit tests still work).

    Safety guard: integration tests MUST have ``.env.test.local`` (written
    by ``make test-db-up``) to prevent accidentally connecting to the main
    Docker Compose database.
    """
    # Safety guard: require .env.test.local for integration tests (local dev only).
    # CI environments (GitHub Actions etc.) set TEST_DB_* vars directly, so skip the guard.
    import os as _os

    _is_ci = _os.environ.get("CI", "").lower() in ("true", "1")
    _has_integration_tests = any(
        "tests/integration" in str(item.fspath) for item in request.session.items
    )
    if _has_integration_tests and not _has_test_env_local and not _is_ci:
        pytest.fail(
            "\n\n"
            "Integration tests require a per-branch test database.\n"
            "No .env.test.local found — this prevents accidentally using\n"
            "the main Docker Compose database.\n\n"
            "Run this first:\n"
            "    make test-db-up\n\n"
            "Then run DB-only integration tests:\n"
            "    make test-integration-db\n\n"
            "For the full test suite (needs Vault, Valkey, MinIO):\n"
            "    make up && make test-integration-full\n"
        )

    db_name = TestConfig.POSTGRES_TEST_DATABASE
    admin_url = TestConfig.get_admin_database_url()

    # CREATE/DROP DATABASE requires autocommit (no transaction block)
    # connect_timeout=3 prevents hanging for minutes when PG is unreachable
    # (macOS stealth-drops packets instead of RST, so default TCP timeout is 75s+)
    engine = create_engine(
        admin_url,
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 3},
    )

    _db_available = False
    try:
        with engine.connect() as conn:
            # Check if database exists
            result = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": db_name},
            )
            exists = result.scalar() is not None

            if not exists:
                _conftest_logger.info("Creating ephemeral test database: %s", db_name)
                conn.execute(text(f'CREATE DATABASE "{db_name}"'))

                # Enable extensions in the new database
                ext_engine = create_engine(
                    admin_url.replace("/postgres", f"/{db_name}"),
                    isolation_level="AUTOCOMMIT",
                )
                try:
                    with ext_engine.connect() as ext_conn:
                        ext_conn.execute(
                            text("CREATE EXTENSION IF NOT EXISTS pgcrypto")
                        )
                        ext_conn.execute(
                            text(
                                "CREATE EXTENSION IF NOT EXISTS pg_partman SCHEMA partman"
                            )
                        )
                finally:
                    ext_engine.dispose()
            else:
                _conftest_logger.info("Using existing test database: %s", db_name)
            _db_available = True
    except Exception as exc:
        if _has_integration_tests:
            # .env.test.local exists (upfront guard passed) but DB unreachable
            pytest.fail(
                f"\n\n"
                f"PostgreSQL is not reachable at "
                f"{TestConfig.POSTGRES_TEST_HOST}:{TestConfig.POSTGRES_TEST_PORT}.\n"
                f".env.test.local exists but the test DB container may have stopped.\n\n"
                f"Try:\n"
                f"    make test-db-status   # check container status\n"
                f"    make test-db-up       # restart the container\n"
            )
        else:
            # Unit-only run — graceful skip (no DB needed)
            _conftest_logger.debug(
                "PostgreSQL not reachable, skipping ephemeral DB setup: %s", exc
            )
    finally:
        engine.dispose()

    yield db_name

    # Teardown: optionally drop the database
    if _db_available and request.config.getoption("--drop-test-db"):
        engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
        try:
            with engine.connect() as conn:
                # Terminate other connections to allow DROP
                conn.execute(
                    text(
                        "SELECT pg_terminate_backend(pid) "
                        "FROM pg_stat_activity "
                        "WHERE datname = :name AND pid != pg_backend_pid()"
                    ),
                    {"name": db_name},
                )
                conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
                _conftest_logger.info("Dropped ephemeral test database: %s", db_name)
        finally:
            engine.dispose()


def seed_system_node_templates_list():
    """Return list of system NodeTemplates for seeding."""

    from analysi.constants import TemplateConstants

    return [
        NodeTemplate(
            id=TemplateConstants.SYSTEM_IDENTITY_TEMPLATE_ID,
            resource_id=TemplateConstants.SYSTEM_IDENTITY_TEMPLATE_ID,
            tenant_id=None,  # System template
            name=TemplateConstants.SYSTEM_IDENTITY_TEMPLATE_NAME,
            description="Identity transformation - passes input through unchanged (T → T)",
            kind="identity",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            code="return inp",
            language="python",
            type="static",
            enabled=True,
            revision_num=1,
        ),
        NodeTemplate(
            id=TemplateConstants.SYSTEM_MERGE_TEMPLATE_ID,
            resource_id=TemplateConstants.SYSTEM_MERGE_TEMPLATE_ID,
            tenant_id=None,
            name=TemplateConstants.SYSTEM_MERGE_TEMPLATE_NAME,
            description="Smart merge - combines objects with field-level conflict detection",
            kind="merge",
            input_schema={"type": "array", "items": {"type": "object"}},
            output_schema={"type": "object"},
            code="""# Deep merge with conflict detection
# Merges objects from parallel branches with support for nested object merging
# Allows branches to add different nested fields under the same parent key

if not isinstance(inp, list) or len(inp) == 0:
    return {}

# Helper to recursively merge two values
def deep_merge(v1, v2, path=""):
    # If both are dicts, merge recursively
    if isinstance(v1, dict) and isinstance(v2, dict):
        result = v1.copy()
        for key in v2:
            new_path = f"{path}.{key}" if path else key
            if key in result:
                # Recursively merge the nested values
                result[key] = deep_merge(result[key], v2[key], new_path)
            else:
                # New key from v2
                result[key] = v2[key]
        return result

    # If both are lists, check if they're equal
    elif isinstance(v1, list) and isinstance(v2, list):
        if v1 == v2:
            return v1  # Same array, no conflict
        else:
            # CONFLICT: different array values
            raise ValueError(
                f"Merge conflict at '{path}': cannot merge different list values. "
                f"Both branches modified the same array field to different values."
            )

    # Different types or primitive values - check if equal
    else:
        # Check equality
        if type(v1) == type(v2) and v1 == v2:
            return v1
        else:
            # CONFLICT: same field, different primitive values or incompatible types
            raise ValueError(
                f"Merge conflict at '{path}': cannot merge {type(v1).__name__} and {type(v2).__name__} "
                f"with different values. Values must match or be mergeable objects/arrays."
            )

# Collect all fields from all branches with deep merging
result = {}

for idx, item in enumerate(inp):
    if not isinstance(item, dict):
        continue

    for key, value in item.items():
        if key in result:
            # Field already exists - deep merge the values
            try:
                result[key] = deep_merge(result[key], value, key)
            except ValueError as e:
                # Re-raise with branch context
                raise ValueError(str(e))
        else:
            # New field - add it
            result[key] = value

return result""",
            language="python",
            type="static",
            enabled=True,
            revision_num=3,
        ),
        NodeTemplate(
            id=TemplateConstants.SYSTEM_COLLECT_TEMPLATE_ID,
            resource_id=TemplateConstants.SYSTEM_COLLECT_TEMPLATE_ID,
            tenant_id=None,
            name=TemplateConstants.SYSTEM_COLLECT_TEMPLATE_NAME,
            description="Collect transformation - aggregates inputs into an array ([T1, T2] → [T1, T2])",
            kind="collect",
            input_schema={"type": "array"},
            output_schema={"type": "array"},
            code="""# Collect all inputs into an array (passthrough for arrays)
if isinstance(inp, list):
    return inp
return [inp]""",
            language="python",
            type="static",
            enabled=True,
            revision_num=1,
        ),
    ]


async def seed_system_node_templates(session: AsyncSession):
    """Seed system NodeTemplates (legacy wrapper)."""
    templates = seed_system_node_templates_list()
    for template in templates:
        session.add(template)
    await session.flush()


async def seed_system_dispositions(session: AsyncSession):
    """Seed system dispositions matching the Flyway migration V015."""
    dispositions = [
        # True Positive (Malicious) - Red/Orange colors
        Disposition(
            category="True Positive (Malicious)",
            subcategory="Confirmed Compromise",
            display_name="Confirmed Compromise",
            color_hex="#DC2626",
            color_name="red",
            priority_score=1,
            description="Active compromise with impact. Immediate incident response required.",
            requires_escalation=True,
            is_system=True,
        ),
        Disposition(
            category="True Positive (Malicious)",
            subcategory="Confirmed Malicious Attempt (Blocked/Prevented, No Impact)",
            display_name="Malicious Attempt Blocked",
            color_hex="#EA580C",
            color_name="orange",
            priority_score=2,
            description="Verified malicious activity, but blocked before causing harm. Important for intel/tuning, but not urgent containment.",
            requires_escalation=False,
            is_system=True,
        ),
        # True Positive (Policy Violation) - Yellow/Orange colors
        Disposition(
            category="True Positive (Policy Violation)",
            subcategory="Acceptable Use Violation (non-security but against policy)",
            display_name="Acceptable Use Violation",
            color_hex="#EAB308",
            color_name="yellow",
            priority_score=5,
            description="Typically HR/management follow-up. Not a direct technical threat.",
            requires_escalation=False,
            is_system=True,
        ),
        Disposition(
            category="True Positive (Policy Violation)",
            subcategory="Unauthorized Access / Privilege Misuse",
            display_name="Unauthorized Access",
            color_hex="#EA580C",
            color_name="orange",
            priority_score=3,
            description="Potential insider threat / misuse. Higher risk than acceptable use violation.",
            requires_escalation=True,
            is_system=True,
        ),
        # False Positive - Yellow colors
        Disposition(
            category="False Positive",
            subcategory="Detection Logic Error",
            display_name="Detection Logic Error",
            color_hex="#EAB308",
            color_name="yellow",
            priority_score=6,
            description="Rule incorrectly designed or triggered. Needs rule fix.",
            requires_escalation=False,
            is_system=True,
        ),
        Disposition(
            category="False Positive",
            subcategory="Rule Misconfiguration / Sensitivity Issue",
            display_name="Rule Misconfiguration",
            color_hex="#EAB308",
            color_name="yellow",
            priority_score=6,
            description="Tuning issue causing noise. Fixable but not dangerous.",
            requires_escalation=False,
            is_system=True,
        ),
        Disposition(
            category="False Positive",
            subcategory="Vendor Signature Bug",
            display_name="Vendor Signature Bug",
            color_hex="#EAB308",
            color_name="yellow",
            priority_score=6,
            description="Upstream/vendor problem. Same urgency as other false positives.",
            requires_escalation=False,
            is_system=True,
        ),
        # Security Testing / Expected Activity - Blue colors
        Disposition(
            category="Security Testing / Expected Activity",
            subcategory="Red Team / Pentest",
            display_name="Red Team Activity",
            color_hex="#2563EB",
            color_name="blue",
            priority_score=8,
            description="Expected malicious-like activity. Needs separation from real incidents.",
            requires_escalation=False,
            is_system=True,
        ),
        Disposition(
            category="Security Testing / Expected Activity",
            subcategory="Compliance / Audit",
            display_name="Compliance Testing",
            color_hex="#2563EB",
            color_name="blue",
            priority_score=8,
            description="Scheduled or approved test activity. Not a threat.",
            requires_escalation=False,
            is_system=True,
        ),
        Disposition(
            category="Security Testing / Expected Activity",
            subcategory="Training / Tabletop",
            display_name="Training Exercise",
            color_hex="#2563EB",
            color_name="blue",
            priority_score=8,
            description="Drill-only alerts. Must be tracked but not triaged as real incidents.",
            requires_escalation=False,
            is_system=True,
        ),
        # Benign Explained - Green colors
        Disposition(
            category="Benign Explained",
            subcategory="Known Business Process",
            display_name="Business Process",
            color_hex="#16A34A",
            color_name="green",
            priority_score=9,
            description="Normal business behavior. Should be documented to avoid future noise.",
            requires_escalation=False,
            is_system=True,
        ),
        Disposition(
            category="Benign Explained",
            subcategory="IT Maintenance / Patch / Scanning",
            display_name="IT Maintenance",
            color_hex="#16A34A",
            color_name="green",
            priority_score=9,
            description="Routine IT activity (patch cycles, admin scripts, scans).",
            requires_escalation=False,
            is_system=True,
        ),
        Disposition(
            category="Benign Explained",
            subcategory="Environmental Noise (e.g., server patching or restart)",
            display_name="Environmental Noise",
            color_hex="#16A34A",
            color_name="green",
            priority_score=9,
            description='Background "chatter" or expected environmental activity.',
            requires_escalation=False,
            is_system=True,
        ),
        # Undetermined - Purple colors
        Disposition(
            category="Undetermined",
            subcategory="Suspicious, Not Confirmed",
            display_name="Suspicious Activity",
            color_hex="#9333EA",
            color_name="purple",
            priority_score=4,
            description="Needs more evidence. Potential threat but not validated.",
            requires_escalation=True,
            is_system=True,
        ),
        Disposition(
            category="Undetermined",
            subcategory="Insufficient Data / Logs Missing",
            display_name="Insufficient Data",
            color_hex="#9333EA",
            color_name="purple",
            priority_score=4,
            description="Cannot confirm due to lack of telemetry. Requires escalation or closure.",
            requires_escalation=True,
            is_system=True,
        ),
        Disposition(
            category="Undetermined",
            subcategory="Escalated for Review",
            display_name="Escalated for Review",
            color_hex="#9333EA",
            color_name="purple",
            priority_score=4,
            description="Passed to Tier 2/3 or specialized team. Unresolved.",
            requires_escalation=True,
            is_system=True,
        ),
        # Analysis Stopped by User - Gray colors
        Disposition(
            category="Analysis Stopped by User",
            subcategory="Invalid Alert",
            display_name="Invalid Alert",
            color_hex="#6B7280",
            color_name="gray",
            priority_score=10,
            description="Analyst stopped analysis due to invalid trigger (e.g., malformed alert).",
            requires_escalation=False,
            is_system=True,
        ),
        Disposition(
            category="Analysis Stopped by User",
            subcategory="Known Issue / Duplicate",
            display_name="Known Issue/Duplicate",
            color_hex="#6B7280",
            color_name="gray",
            priority_score=10,
            description="Duplicate alert, or already tracked incident. Closed administratively.",
            requires_escalation=False,
            is_system=True,
        ),
    ]

    for disp in dispositions:
        session.add(disp)
    await session.flush()


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# Unit test engine: same cached-setup pattern as integration engine
# ---------------------------------------------------------------------------
_unit_test_setup_done = False


@pytest_asyncio.fixture(scope="function")
async def test_engine():
    """Create a test database engine for unit tests (PostgreSQL).

    Uses cached one-time setup pattern (same as integration_test_engine).
    """
    global _unit_test_setup_done

    database_url = TestConfig.get_test_database_url()

    engine = create_async_engine(
        database_url,
        echo=False,
        pool_size=5,
        max_overflow=5,
        pool_pre_ping=True,
        pool_recycle=3600,
    )

    if not _unit_test_setup_done:
        from tests.utils.db_cleanup import PartitionLifecycleManager

        # Create all tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # Seed system node templates
        async_session = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        async with async_session() as session:
            from sqlalchemy import delete

            await session.execute(
                delete(NodeTemplate).where(NodeTemplate.tenant_id.is_(None))
            )
            await session.commit()
            await seed_system_node_templates(session)
            await session.commit()
            session.expire_all()

        # Create partitions
        async with async_session() as session:
            try:
                await PartitionLifecycleManager.ensure_test_partitions(
                    session=session,
                    days_past=1,
                    days_future=7,
                    cleanup_old=True,
                    keep_days=14,
                )
            except Exception as e:
                import logging

                logging.debug("Partition setup skipped during test setup: %s", e)

        _unit_test_setup_done = True

    yield engine

    # Dispose engine to release connections
    try:
        await engine.dispose()
        await asyncio.sleep(0.1)
    except RuntimeError as e:
        if "Event loop is closed" in str(e):
            pass
        else:
            raise


# ---------------------------------------------------------------------------
# Integration engine: function-scoped fixture with cached one-time setup
# ---------------------------------------------------------------------------
# The expensive operations (create_all, seed dispositions, seed templates,
# partition lifecycle) are idempotent and only need to run once per test run.
# We track this with a module-level flag to skip them on subsequent calls.
# The engine itself is cheap to create/dispose per test (~100ms), but the
# setup above was adding ~2-3s per test × 1800 tests = ~90 min overhead.
_integration_setup_done = False


@pytest_asyncio.fixture(scope="function")
async def integration_test_engine():
    """Create a test database engine for integration tests (PostgreSQL).

    Engine is created per-test (required for event loop compatibility), but
    expensive one-time setup (create_all, seeding, partitions) is cached
    and only runs on the first invocation.
    """
    global _integration_setup_done

    database_url = IntegrationTestConfig.get_database_url()

    engine = create_async_engine(
        database_url,
        echo=False,
        pool_size=5,
        max_overflow=5,
        pool_pre_ping=True,
        pool_recycle=3600,
    )

    if not _integration_setup_done:
        from tests.utils.db_cleanup import PartitionLifecycleManager

        # Create all tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async_session = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

        # Seed system dispositions (idempotent)
        async with async_session() as session:
            from sqlalchemy import select

            result = await session.execute(
                select(Disposition).where(Disposition.is_system.is_(True))
            )
            if not result.scalars().first():
                await seed_system_dispositions(session)
                await session.commit()

        # Seed system node templates (upsert, idempotent)
        async with async_session() as session:
            from sqlalchemy import select

            templates_to_seed = seed_system_node_templates_list()
            for template in templates_to_seed:
                existing = await session.execute(
                    select(NodeTemplate).where(NodeTemplate.id == template.id)
                )
                existing_template = existing.scalar_one_or_none()
                if existing_template:
                    for key, value in template.__dict__.items():
                        if not key.startswith("_"):
                            setattr(existing_template, key, value)
                else:
                    session.add(template)
            await session.commit()
            session.expire_all()

        # Create partitions (with cleanup of old ones)
        async with async_session() as session:
            try:
                await PartitionLifecycleManager.ensure_test_partitions(
                    session=session,
                    days_past=1,
                    days_future=7,
                    cleanup_old=True,
                    keep_days=14,
                )
            except Exception as e:
                import logging

                logging.debug("Partition setup skipped during test setup: %s", e)

        _integration_setup_done = True

    yield engine

    # Dispose engine to release connections back to the pool
    try:
        await engine.dispose()
        await asyncio.sleep(0.1)
    except RuntimeError as e:
        if "Event loop is closed" in str(e):
            pass
        else:
            raise


@pytest_asyncio.fixture(scope="function")
async def integration_test_session(
    integration_test_engine,
) -> AsyncGenerator[AsyncSession]:
    """Create an integration test database session (PostgreSQL).

    Uses centralized utilities from tests.utils.db_cleanup for DRY cleanup.
    """
    from tests.utils.db_cleanup import TestDatabaseCleaner

    async_session = async_sessionmaker(
        integration_test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        try:
            yield session
        finally:
            # Clean up any uncommitted changes
            try:
                await session.rollback()
            except Exception as e:
                # During teardown, ignore transaction errors that can occur
                # when there are concurrent operations or session conflicts
                import logging

                logger = logging.getLogger(__name__)
                logger.debug("Ignoring rollback error during test teardown: %s", e)

            # Clean up data using centralized cleanup utility (DRY)
            try:
                await TestDatabaseCleaner.clean_all_tables(
                    session=session,
                    preserve_system_data=True,  # Keep system templates and dispositions
                )
            except Exception as e:
                # Ignore commit errors during cleanup
                import logging

                logger = logging.getLogger(__name__)
                logger.debug("Ignoring commit error during test cleanup: %s", e)


@pytest_asyncio.fixture(scope="function")
async def test_session(test_engine) -> AsyncGenerator[AsyncSession]:
    """Create a test database session.

    Uses centralized utilities from tests.utils.db_cleanup for DRY cleanup.
    """
    from tests.utils.db_cleanup import TestDatabaseCleaner

    async_session = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        try:
            yield session
        finally:
            # Clean up any uncommitted changes
            try:
                await session.rollback()
            except Exception as e:
                # During teardown, ignore transaction errors that can occur
                # when there are concurrent operations or session conflicts
                import logging

                logger = logging.getLogger(__name__)
                logger.debug("Ignoring rollback error during test teardown: %s", e)

            # Clean up data using centralized cleanup utility (DRY)
            try:
                await TestDatabaseCleaner.clean_all_tables(
                    session=session,
                    preserve_system_data=True,  # Keep system templates
                )
            except Exception as e:
                # Ignore commit errors during cleanup
                import logging

                logger = logging.getLogger(__name__)
                logger.debug("Ignoring commit error during test cleanup: %s", e)


# Unit test fixtures (no database required)
@pytest.fixture
def sample_tenant_id():
    """Generate a sample tenant ID for tests."""
    return "default"


@pytest.fixture
def sample_component_id():
    """Generate a sample component ID for tests."""
    return uuid4()


# Alias for compatibility with tests expecting db_session
@pytest_asyncio.fixture(scope="function")
async def db_session(test_session) -> AsyncGenerator[AsyncSession]:
    """Alias for test_session for backward compatibility."""
    yield test_session


@pytest.fixture
def sample_tenants():
    """Provide sample tenant IDs for tests."""
    return [
        "default",
        "tenant-123",
        "customer_abc",
        "org-security-team",
        "test_tenant_2024",
    ]


@pytest.fixture
def sample_task_data():
    """Provide sample task data for tests."""
    return {
        "name": "Test Security Alert Analysis",
        "description": "Analyzes security alerts for threats",
        "script": "TASK analyze_alert:\n  INPUT: alert_data\n  PROCESS: threat_detection\n  OUTPUT: analysis_result",
        "directive": "Analyze security alerts for potential threats",
        "function": "reasoning",
        "scope": "processing",
        "llm_config": {"model": "gpt-4", "temperature": 0.7},
    }


@pytest_asyncio.fixture(scope="function")
async def minio_test_bucket():
    """Create and cleanup a test bucket for Minio integration tests."""
    import aiobotocore.session
    from botocore.exceptions import ClientError

    from analysi.config.object_storage import ObjectStorageConfig

    # Single source of truth for object storage config
    config = ObjectStorageConfig.get_settings(test_mode=True)
    endpoint = config["endpoint"]
    if not endpoint.startswith("http"):
        endpoint = f"http://{endpoint}"
    access_key = config["access_key"]
    secret_key = config["secret_key"]
    bucket_name = config["bucket"]

    session = aiobotocore.session.get_session()

    async with session.create_client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="us-east-1",
    ) as s3_client:
        # Create bucket if it doesn't exist
        try:
            await s3_client.head_bucket(Bucket=bucket_name)
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                await s3_client.create_bucket(Bucket=bucket_name)

        yield bucket_name

        # Cleanup: Delete all objects in bucket (but keep bucket for performance)
        try:
            # List and delete all objects
            response = await s3_client.list_objects_v2(Bucket=bucket_name)
            if "Contents" in response:
                objects = [{"Key": obj["Key"]} for obj in response["Contents"]]
                if objects:
                    await s3_client.delete_objects(
                        Bucket=bucket_name, Delete={"Objects": objects}
                    )
        except ClientError:
            # Ignore cleanup errors
            pass


@pytest_asyncio.fixture(scope="function", autouse=True)
async def cleanup_shared_singletons():
    """
    Reset module-level singletons between tests to prevent event loop issues.

    pytest-asyncio creates a new event loop per test function. Module-level
    singletons (DB engine, ARQ pool) may hold references to a previous
    loop's connections, causing "Event loop is closed" errors.

    This fixture resets them after each test so the next test creates
    fresh instances on its own event loop.
    """
    yield

    # Reset ARQ pool singleton — prevents "Event loop is closed" when
    # the next test tries to enqueue via a pool bound to a dead loop.
    from analysi.common.arq_enqueue import reset_pool

    reset_pool()

    # Dispose the shared engine used by MCP tools
    try:
        from analysi.db.session import engine

        await engine.dispose()
    except RuntimeError as e:
        # Ignore "Event loop is closed" during test teardown
        if "Event loop is closed" not in str(e):
            raise
    except Exception:
        # Ignore other disposal errors during test cleanup
        pass


# ---------------------------------------------------------------------------
# Auth override
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def override_auth():
    """Inject a platform_admin CurrentUser into all tests.

    Uses platform_admin (tenant_id=None) rather than a fixed tenant_id so
    that the ~150 existing integration tests that use different tenant IDs in
    URL paths (/v1/default/..., /v1/test_tenant/..., etc.) all continue to
    pass when RBAC enforces current_user.tenant_id == url tenant_id.
    platform_admin bypasses the tenant check entirely.

    Tests that need a specific role can locally override:
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(roles=["viewer"], ...)
    """
    from analysi.auth.dependencies import get_current_user
    from analysi.auth.models import CurrentUser
    from analysi.main import app

    test_user = CurrentUser(
        user_id="test-user-id",
        email="test@analysi.local",
        tenant_id=None,
        roles=["platform_admin"],
        actor_type="user",
    )
    app.dependency_overrides[get_current_user] = lambda: test_user
    yield
    app.dependency_overrides.pop(get_current_user, None)
