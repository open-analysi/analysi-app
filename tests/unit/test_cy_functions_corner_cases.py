"""Corner-case unit tests for ``analysi.services.cy_functions``.

The main suite (``tests/unit/test_cy_functions.py``) covers the happy path
plus HTTP-level errors. This file fills the remaining gaps in the
``CyArtifactFunctions`` helpers — specifically:

- ``_prepare_content_for_storage`` non-dict/str/bytes fallback (line 282)
- ``_convert_tags_to_list`` single-value fallback (line 305)
- ``store_artifact`` UUID-coercion edge cases (the inner ``safe_uuid`` branches)
- ``store_artifact`` orphan-artifact path that synthesises an analysis_id
"""

from __future__ import annotations

from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest

from analysi.services.artifact_service import ArtifactService
from analysi.services.cy_functions import CyArtifactFunctions

# ── fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def cy(execution_context: dict) -> CyArtifactFunctions:
    service = Mock(spec=ArtifactService)
    return CyArtifactFunctions(service, execution_context)


@pytest.fixture
def execution_context() -> dict:
    return {
        "tenant_id": "test-tenant",
        "task_id": str(uuid4()),
        "task_run_id": str(uuid4()),
        "workflow_id": None,
        "workflow_run_id": None,
        "workflow_node_instance_id": None,
        "analysis_id": None,
    }


# ── _prepare_content_for_storage ────────────────────────────────────────────


def test_prepare_content_for_storage_int_falls_back_to_str(
    cy: CyArtifactFunctions,
) -> None:
    """Anything that's not dict / str / bytes is coerced via ``str()``.

    This covers the trailing fallback at line 282 of cy_functions.py.
    """
    assert cy._prepare_content_for_storage(42) == "42"


def test_prepare_content_for_storage_list_falls_back_to_str(
    cy: CyArtifactFunctions,
) -> None:
    out = cy._prepare_content_for_storage([1, 2, 3])
    assert out == "[1, 2, 3]"


def test_prepare_content_for_storage_none_falls_back_to_str(
    cy: CyArtifactFunctions,
) -> None:
    """``None`` content shouldn't crash — we just stringify it."""
    assert cy._prepare_content_for_storage(None) == "None"


# ── _convert_tags_to_list ───────────────────────────────────────────────────


def test_convert_tags_to_list_string_wraps_in_list(cy: CyArtifactFunctions) -> None:
    """Plain-string tag is wrapped in a list. (Covers line 305 fallback.)"""
    assert cy._convert_tags_to_list("solo-tag") == ["solo-tag"]


def test_convert_tags_to_list_int_wraps_in_list(cy: CyArtifactFunctions) -> None:
    assert cy._convert_tags_to_list(42) == ["42"]


def test_convert_tags_to_list_dict_with_int_values(cy: CyArtifactFunctions) -> None:
    """Dict values that aren't strings still serialize cleanly."""
    out = cy._convert_tags_to_list({"priority": 5, "active": True})
    assert sorted(out) == ["active:True", "priority:5"]


def test_convert_tags_to_list_empty_list(cy: CyArtifactFunctions) -> None:
    assert cy._convert_tags_to_list([]) == []


def test_convert_tags_to_list_empty_dict(cy: CyArtifactFunctions) -> None:
    assert cy._convert_tags_to_list({}) == []


# ── store_artifact UUID-coercion paths ─────────────────────────────────────-


@pytest.mark.asyncio
async def test_store_artifact_passes_uuid_object_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``safe_uuid`` short-circuits when given an actual UUID object —
    covers ``isinstance(value, UUID): return value`` (line 78)."""
    captured: dict = {}

    async def fake_post(self, tenant_id, artifact_data):
        captured["task_run_id"] = artifact_data.task_run_id
        return "art-1"

    monkeypatch.setattr(
        CyArtifactFunctions, "_create_artifact_via_async_api", fake_post
    )

    task_run_uuid = uuid4()
    cy = CyArtifactFunctions(
        Mock(spec=ArtifactService),
        {"tenant_id": "t", "task_run_id": task_run_uuid},
    )
    await cy.store_artifact(name="a", artifact="hello")
    assert captured["task_run_id"] == task_run_uuid


@pytest.mark.asyncio
async def test_store_artifact_synthesizes_analysis_id_when_context_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When no relationship IDs are present, ``store_artifact`` synthesizes
    a fresh analysis_id (lines 113-116)."""
    captured: dict = {}

    async def fake_post(self, tenant_id, artifact_data):
        captured["analysis_id"] = artifact_data.analysis_id
        captured["task_run_id"] = artifact_data.task_run_id
        return "art-2"

    monkeypatch.setattr(
        CyArtifactFunctions, "_create_artifact_via_async_api", fake_post
    )

    cy = CyArtifactFunctions(
        Mock(spec=ArtifactService),
        {
            "tenant_id": "t",
            # all relationship fields absent (None / missing)
            "task_run_id": None,
            "workflow_run_id": None,
            "workflow_node_instance_id": None,
            "analysis_id": None,
        },
    )
    await cy.store_artifact(name="a", artifact="hello")

    assert captured["task_run_id"] is None
    assert isinstance(captured["analysis_id"], UUID)


@pytest.mark.asyncio
async def test_store_artifact_invalid_taskrun_uuid_swallowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``safe_uuid`` swallows ValueError/TypeError and returns None when
    given a non-UUID string. Covers lines 80-81 of cy_functions.py.
    The orphan-fallback branch then re-tries the same context value, which
    again coerces to None — net result: artifact is created with all
    relationship IDs None, no crash."""
    captured: dict = {}

    async def fake_post(self, tenant_id, artifact_data):
        captured["task_run_id"] = artifact_data.task_run_id
        captured["analysis_id"] = artifact_data.analysis_id
        return "art-2b"

    monkeypatch.setattr(
        CyArtifactFunctions, "_create_artifact_via_async_api", fake_post
    )
    cy = CyArtifactFunctions(
        Mock(spec=ArtifactService),
        {
            "tenant_id": "t",
            "task_run_id": "not-a-uuid",
            "workflow_run_id": None,
            "workflow_node_instance_id": None,
            "analysis_id": None,
        },
    )
    await cy.store_artifact(name="a", artifact="hello")
    assert captured["task_run_id"] is None
    # Analysis_id is NOT synthesised here because the truthy ``task_run_id``
    # context value sends us into the "if" branch (which fails parsing).
    assert captured["analysis_id"] is None


@pytest.mark.asyncio
async def test_store_artifact_falls_back_to_taskrun_when_truthy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If all *parsed* UUIDs are None but ``task_run_id`` in context is
    truthy (just unparsable), the orphan branch re-tries the task_run_id
    coercion. Covers line 110-111."""

    async def fake_post(self, tenant_id, artifact_data):
        # Both parses fail, so task_run_id stays None and we fall through
        # to the synthesized analysis_id branch.
        return "art-3"

    monkeypatch.setattr(
        CyArtifactFunctions, "_create_artifact_via_async_api", fake_post
    )
    cy = CyArtifactFunctions(
        Mock(spec=ArtifactService),
        {
            "tenant_id": "t",
            "task_run_id": "not-a-uuid",
            "workflow_run_id": None,
            "workflow_node_instance_id": None,
            "analysis_id": None,
        },
    )
    # Should not raise.
    assert await cy.store_artifact(name="x", artifact="y") == "art-3"
