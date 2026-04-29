"""Unit tests for ``analysi.data.cim_mappings``.

``CIMMappingLoader`` reads three KU tables (source-category → CIM datamodel,
CIM datamodel → sourcetypes, sourcetype → index) and reshapes them into
dicts the SPL generator can join. The DB is mocked here — we're testing
the row-reshaping logic and the per-method caches, neither of which is
exercised end-to-end by integration tests today (combined coverage was
11 % on this file).

Heavy use of namespaces (``hasattr(session, "_is_closed")``) means we
mock with plain ``MagicMock`` and stub the KU service rather than a real
SQLAlchemy session.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from analysi.data.cim_mappings import CIMMappingLoader

# ── helpers ────────────────────────────────────────────────────────────────-


def _make_table(rows: list[dict]) -> SimpleNamespace:
    """Build a stand-in for the KU table object the loader expects."""
    return SimpleNamespace(content={"rows": rows})


def _make_loader(table_or_factory=None) -> CIMMappingLoader:
    """Build a loader whose KU service returns either a single table for
    every name, or — if a callable — whatever the callable returns when
    given the table name.

    The session is built with ``spec=[]`` so ``hasattr(session,
    "_is_closed")`` is False (the loader interprets a missing
    ``_is_closed`` as "session is fine"). Tests that exercise the
    "session closed" branch construct their own session with
    ``_is_closed = True``.
    """
    session = MagicMock(spec=[])
    loader = CIMMappingLoader(session=session, tenant_id="t-1")

    async def get_table_by_name_or_id(_tenant, name=None, **_kw):
        if callable(table_or_factory):
            return table_or_factory(name)
        return table_or_factory

    loader.ku_service = MagicMock()
    loader.ku_service.get_table_by_name_or_id = AsyncMock(
        side_effect=get_table_by_name_or_id
    )
    return loader


# ── load_source_to_cim_mappings ────────────────────────────────────────────-


@pytest.mark.asyncio
async def test_source_to_cim_happy_with_canonical_names() -> None:
    table = _make_table(
        [
            {
                "source_category": "Firewall",
                "primary_cim_datamodel": "Network Traffic",
                "secondary_cim_models": ["Network Sessions"],
            },
            {
                "source_category": "Authentication",
                "primary_cim_datamodel": "Authentication",
                "secondary_cim_models": [],
            },
        ]
    )
    loader = _make_loader(table)
    out = await loader.load_source_to_cim_mappings()
    assert out["Firewall"]["primary_cim_datamodel"] == "Network Traffic"
    assert out["Firewall"]["secondary_cim_models"] == ["Network Sessions"]
    assert out["Authentication"]["secondary_cim_models"] == []


@pytest.mark.asyncio
async def test_source_to_cim_uses_legacy_field_name_fallback() -> None:
    """Older tenants stored the column as ``nas_source_category``."""
    table = _make_table(
        [
            {
                "nas_source_category": "Firewall",
                "primary_cim_datamodel": "Network Traffic",
            }
        ]
    )
    loader = _make_loader(table)
    out = await loader.load_source_to_cim_mappings()
    assert "Firewall" in out


@pytest.mark.asyncio
async def test_source_to_cim_skips_rows_without_category() -> None:
    table = _make_table(
        [
            {"primary_cim_datamodel": "Network Traffic"},  # no category — drop
            {"source_category": "Firewall", "primary_cim_datamodel": "Network"},
        ]
    )
    loader = _make_loader(table)
    out = await loader.load_source_to_cim_mappings()
    assert list(out.keys()) == ["Firewall"]


@pytest.mark.asyncio
async def test_source_to_cim_caches_after_first_call() -> None:
    table = _make_table([{"source_category": "X", "primary_cim_datamodel": "Y"}])
    loader = _make_loader(table)
    await loader.load_source_to_cim_mappings()
    await loader.load_source_to_cim_mappings()
    # KU service called once even though we asked twice.
    assert loader.ku_service.get_table_by_name_or_id.await_count == 1


@pytest.mark.asyncio
async def test_source_to_cim_falls_back_to_legacy_table_name() -> None:
    """If the canonical-name table is missing, the loader retries with the
    legacy table name (``Splunk: NAS Sources to CIM Datamodel Mappings``)."""
    canonical = "Splunk: Source Category to CIM Datamodel Mappings"
    legacy = "Splunk: NAS Sources to CIM Datamodel Mappings"

    def factory(name: str):
        if name == canonical:
            return None
        if name == legacy:
            return _make_table(
                [{"source_category": "F", "primary_cim_datamodel": "X"}]
            )
        return None

    loader = _make_loader(factory)
    out = await loader.load_source_to_cim_mappings()
    assert "F" in out


@pytest.mark.asyncio
async def test_source_to_cim_missing_table_raises() -> None:
    """If neither the canonical nor legacy table exists, raise."""
    loader = _make_loader(None)
    with pytest.raises(ValueError, match="not found for tenant"):
        await loader.load_source_to_cim_mappings()


@pytest.mark.asyncio
async def test_source_to_cim_swallows_teardown_errors() -> None:
    """Specific transaction-teardown errors return an empty mapping
    rather than propagating — protects test fixtures from cascading
    failures."""
    loader = _make_loader()
    loader.ku_service.get_table_by_name_or_id = AsyncMock(
        side_effect=RuntimeError("connection is closed")
    )
    out = await loader.load_source_to_cim_mappings()
    assert out == {}


@pytest.mark.asyncio
async def test_source_to_cim_session_closed_check() -> None:
    """If the session has ``_is_closed = True``, the loader fails fast
    with a descriptive ValueError."""
    session = MagicMock()
    session._is_closed = True
    loader = CIMMappingLoader(session=session, tenant_id="t-1")
    loader.ku_service = MagicMock()
    with pytest.raises(ValueError, match="Session closed"):
        await loader.load_source_to_cim_mappings()


# ── load_cim_to_sourcetypes_mappings ───────────────────────────────────────-


@pytest.mark.asyncio
async def test_cim_to_sourcetypes_happy() -> None:
    table = _make_table(
        [
            {
                "datamodel": "Authentication",
                "sourcetypes": ["WinEventLog:*", "aws:cloudtrail"],
                "datamodel_id": "dm_002",
                "sourcetype_count": 34,
            }
        ]
    )
    loader = _make_loader(table)
    out = await loader.load_cim_to_sourcetypes_mappings()
    assert out["Authentication"]["sourcetypes"] == [
        "WinEventLog:*",
        "aws:cloudtrail",
    ]
    assert out["Authentication"]["sourcetype_count"] == 34


@pytest.mark.asyncio
async def test_cim_to_sourcetypes_uses_cim_datamodel_alias() -> None:
    """Some tables use ``cim_datamodel`` instead of ``datamodel``."""
    table = _make_table(
        [{"cim_datamodel": "Web", "sourcetypes": ["access_combined"]}]
    )
    loader = _make_loader(table)
    out = await loader.load_cim_to_sourcetypes_mappings()
    assert "Web" in out


@pytest.mark.asyncio
async def test_cim_to_sourcetypes_caches() -> None:
    table = _make_table([{"datamodel": "X", "sourcetypes": []}])
    loader = _make_loader(table)
    await loader.load_cim_to_sourcetypes_mappings()
    await loader.load_cim_to_sourcetypes_mappings()
    assert loader.ku_service.get_table_by_name_or_id.await_count == 1


@pytest.mark.asyncio
async def test_cim_to_sourcetypes_missing_table_raises() -> None:
    loader = _make_loader(None)
    with pytest.raises(ValueError, match="not found for tenant"):
        await loader.load_cim_to_sourcetypes_mappings()


@pytest.mark.asyncio
async def test_cim_to_sourcetypes_swallows_teardown() -> None:
    loader = _make_loader()
    loader.ku_service.get_table_by_name_or_id = AsyncMock(
        side_effect=RuntimeError("another operation is in progress")
    )
    assert await loader.load_cim_to_sourcetypes_mappings() == {}


@pytest.mark.asyncio
async def test_cim_to_sourcetypes_skips_rows_without_datamodel() -> None:
    table = _make_table(
        [
            {"sourcetypes": ["wineventlog"]},  # no datamodel — drop
            {"datamodel": "X", "sourcetypes": ["wineventlog"]},
        ]
    )
    loader = _make_loader(table)
    out = await loader.load_cim_to_sourcetypes_mappings()
    assert list(out.keys()) == ["X"]


# ── load_sourcetype_to_index_directory ─────────────────────────────────────-


@pytest.mark.asyncio
async def test_sourcetype_to_index_happy() -> None:
    table = _make_table(
        [
            {
                "sourcetype": "pan:threat",
                "index": "main",
                "eps_count": 15.0,
                "latest": 1758670143,
                "earliest": 1758587484,
                "time_span_seconds": 82.659,
            }
        ]
    )
    loader = _make_loader(table)
    out = await loader.load_sourcetype_to_index_directory()
    assert out["pan:threat"]["index"] == "main"
    assert out["pan:threat"]["eps_count"] == 15.0


@pytest.mark.asyncio
async def test_sourcetype_to_index_eps_alias() -> None:
    """Older rows used ``eps`` instead of ``eps_count`` — the loader
    accepts either."""
    table = _make_table(
        [
            {"sourcetype": "x", "index": "main", "eps": 99.0},
        ]
    )
    loader = _make_loader(table)
    out = await loader.load_sourcetype_to_index_directory()
    assert out["x"]["eps_count"] == 99.0


@pytest.mark.asyncio
async def test_sourcetype_to_index_caches() -> None:
    table = _make_table([{"sourcetype": "x", "index": "main"}])
    loader = _make_loader(table)
    await loader.load_sourcetype_to_index_directory()
    await loader.load_sourcetype_to_index_directory()
    assert loader.ku_service.get_table_by_name_or_id.await_count == 1


@pytest.mark.asyncio
async def test_sourcetype_to_index_missing_table_raises() -> None:
    loader = _make_loader(None)
    with pytest.raises(ValueError, match="not found for tenant"):
        await loader.load_sourcetype_to_index_directory()


@pytest.mark.asyncio
async def test_sourcetype_to_index_swallows_teardown() -> None:
    loader = _make_loader()
    loader.ku_service.get_table_by_name_or_id = AsyncMock(
        side_effect=RuntimeError(
            "cannot use connection.transaction() in a manually started transaction"
        )
    )
    assert await loader.load_sourcetype_to_index_directory() == {}


@pytest.mark.asyncio
async def test_sourcetype_to_index_skips_rows_without_sourcetype() -> None:
    table = _make_table(
        [
            {"index": "main"},  # no sourcetype — drop
            {"sourcetype": "x", "index": "main"},
        ]
    )
    loader = _make_loader(table)
    out = await loader.load_sourcetype_to_index_directory()
    assert list(out.keys()) == ["x"]


@pytest.mark.asyncio
async def test_sourcetype_to_index_eps_count_default_zero() -> None:
    """Missing eps in row → default 0."""
    table = _make_table([{"sourcetype": "x", "index": "main"}])
    loader = _make_loader(table)
    out = await loader.load_sourcetype_to_index_directory()
    assert out["x"]["eps_count"] == 0


@pytest.mark.asyncio
async def test_unrelated_runtime_error_is_propagated() -> None:
    """Errors NOT in the teardown allow-list propagate."""
    loader = _make_loader()
    loader.ku_service.get_table_by_name_or_id = AsyncMock(
        side_effect=RuntimeError("unexpected DB driver error")
    )
    with pytest.raises(RuntimeError, match="unexpected DB driver error"):
        await loader.load_sourcetype_to_index_directory()
