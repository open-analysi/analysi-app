"""Hardening tests for skill validation entry points.

Tests error handling, edge cases, and security properties of the
link_document and stage_document validation wiring.
"""

import io
import json
import os
import uuid
import zipfile
from collections.abc import AsyncGenerator
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.db.session import get_db
from analysi.main import app


def _make_zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


@pytest.mark.asyncio
@pytest.mark.integration
class TestSkillValidationHardening:
    """Hardening tests for validation entry points."""

    @pytest_asyncio.fixture
    async def client(
        self, integration_test_session: AsyncSession
    ) -> AsyncGenerator[AsyncClient]:
        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        env_patch = patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""})
        env_patch.start()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            suffix = uuid.uuid4().hex[:8]
            tenant = f"test-val-hardening-{suffix}"

            # Create a skill
            skill_resp = await client.post(
                f"/v1/{tenant}/skills",
                json={
                    "name": f"Hardening Skill {suffix}",
                    "description": "Skill for hardening tests",
                },
            )
            assert skill_resp.status_code == 201

            # Create a normal document
            doc_resp = await client.post(
                f"/v1/{tenant}/knowledge-units/documents",
                json={
                    "name": f"Test Doc {suffix}",
                    "content": "# Safe Content\n\nNothing suspicious here.",
                    "doc_format": "markdown",
                    "document_type": "soar_playbook",
                },
            )
            assert doc_resp.status_code == 201

            client._test_tenant = tenant
            client._test_skill_id = skill_resp.json()["data"]["id"]
            client._test_doc_id = doc_resp.json()["data"]["id"]
            client._test_session = integration_test_session

            yield client

        env_patch.stop()
        app.dependency_overrides.clear()

    # --- Error message tests ---

    async def test_link_gate_failure_does_not_leak_internals(self, client):
        """422 from content gate should not expose internal error details."""
        tenant = client._test_tenant
        skill_id = client._test_skill_id

        # Create a document with suspicious content
        doc_resp = await client.post(
            f"/v1/{tenant}/knowledge-units/documents",
            json={
                "name": "Evil Doc",
                "content": "```python\nimport os\nos.system('rm -rf /')\n```",
                "doc_format": "markdown",
                "document_type": "soar_playbook",
            },
        )
        evil_doc_id = doc_resp.json()["data"]["id"]

        resp = await client.post(
            f"/v1/{tenant}/skills/{skill_id}/documents",
            json={
                "document_id": evil_doc_id,
                "namespace_path": "docs/evil.md",
            },
        )
        assert resp.status_code == 422
        detail = resp.json().get("detail", "")
        # Should not contain file paths, stack traces, or internal class names
        assert "Traceback" not in detail
        assert "/Users/" not in detail
        assert "analysi" not in detail

    async def test_stage_gate_failure_does_not_leak_internals(self, client):
        """Same gate check for stage_document endpoint."""
        tenant = client._test_tenant
        skill_id = client._test_skill_id

        doc_resp = await client.post(
            f"/v1/{tenant}/knowledge-units/documents",
            json={
                "name": "Evil Staged",
                "content": "```python\neval('bad')\n```",
                "doc_format": "markdown",
                "document_type": "soar_playbook",
            },
        )
        evil_doc_id = doc_resp.json()["data"]["id"]

        resp = await client.post(
            f"/v1/{tenant}/skills/{skill_id}/staged-documents",
            json={
                "document_id": evil_doc_id,
                "namespace_path": "staged/evil.md",
            },
        )
        assert resp.status_code == 422
        detail = resp.json().get("detail", "")
        assert "Traceback" not in detail
        assert "/Users/" not in detail

    # --- Validation still allows safe content ---

    async def test_link_safe_content_succeeds(self, client):
        """Safe content linking should create a validation review and succeed."""
        resp = await client.post(
            f"/v1/{client._test_tenant}/skills/{client._test_skill_id}/documents",
            json={
                "document_id": client._test_doc_id,
                "namespace_path": "docs/safe.md",
            },
        )
        assert resp.status_code == 201

    async def test_stage_safe_content_succeeds(self, client):
        """Safe content staging should create a validation review and succeed."""
        # Create a second doc for staging
        doc_resp = await client.post(
            f"/v1/{client._test_tenant}/knowledge-units/documents",
            json={
                "name": "Safe Stage Doc",
                "content": "# Safe\n\nJust a guide.",
                "doc_format": "markdown",
                "document_type": "soar_playbook",
            },
        )
        doc_id = doc_resp.json()["data"]["id"]

        resp = await client.post(
            f"/v1/{client._test_tenant}/skills/{client._test_skill_id}/staged-documents",
            json={"document_id": doc_id, "namespace_path": "staged/safe.md"},
        )
        assert resp.status_code == 201

    # --- Nonexistent resources ---

    async def test_link_to_nonexistent_skill_returns_404(self, client):
        """Linking to a nonexistent skill should return 404."""
        fake_skill_id = str(uuid.uuid4())
        resp = await client.post(
            f"/v1/{client._test_tenant}/skills/{fake_skill_id}/documents",
            json={
                "document_id": client._test_doc_id,
                "namespace_path": "docs/test.md",
            },
        )
        assert resp.status_code == 404

    async def test_stage_to_nonexistent_skill_returns_404(self, client):
        """Staging to a nonexistent skill should return 404."""
        fake_skill_id = str(uuid.uuid4())
        resp = await client.post(
            f"/v1/{client._test_tenant}/skills/{fake_skill_id}/staged-documents",
            json={
                "document_id": client._test_doc_id,
                "namespace_path": "staged/test.md",
            },
        )
        assert resp.status_code == 404


@pytest.mark.asyncio
@pytest.mark.integration
class TestImportHardening:
    """Hardening tests for zip import endpoint."""

    @pytest_asyncio.fixture
    async def client(
        self, integration_test_session: AsyncSession
    ) -> AsyncGenerator[AsyncClient]:
        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        env_patch = patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""})
        env_patch.start()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            suffix = uuid.uuid4().hex[:8]
            client._test_tenant = f"test-import-hard-{suffix}"
            client._test_suffix = suffix
            yield client

        env_patch.stop()
        app.dependency_overrides.clear()

    async def test_path_traversal_in_zip_rejected(self, client):
        """Zip with ../ paths should be rejected."""
        suffix = client._test_suffix
        zip_bytes = _make_zip(
            {
                "manifest.json": json.dumps(
                    {
                        "name": f"Evil Skill {suffix}",
                        "description": "Path traversal attempt",
                        "version": "1.0.0",
                        "cy_name": f"evil_{suffix}",
                        "categories": [],
                        "config": {},
                    }
                ),
                "SKILL.md": "# Evil\n\nPath traversal.",
                "../../../etc/passwd": "root:x:0:0",
            }
        )

        resp = await client.post(
            f"/v1/{client._test_tenant}/skills/import",
            files={"file": ("evil.zip", zip_bytes, "application/zip")},
        )
        assert resp.status_code == 422
        assert (
            "traversal" in resp.json()["detail"].lower()
            or "path" in resp.json()["detail"].lower()
        )

    async def test_import_error_detail_does_not_leak_paths(self, client):
        """Import errors should not expose server file paths."""
        zip_bytes = _make_zip(
            {
                "manifest.json": "not valid json{{{",
                "SKILL.md": "# Test",
            }
        )

        resp = await client.post(
            f"/v1/{client._test_tenant}/skills/import",
            files={"file": ("bad.zip", zip_bytes, "application/zip")},
        )
        assert resp.status_code == 422
        detail = resp.json().get("detail", "")
        assert "/Users/" not in detail
        assert "analysi" not in detail

    async def test_extensionless_file_rejected(self, client):
        """Zip with extensionless file should be rejected."""
        suffix = client._test_suffix
        zip_bytes = _make_zip(
            {
                "manifest.json": json.dumps(
                    {
                        "name": f"Ext Skill {suffix}",
                        "description": "Has Makefile",
                        "version": "1.0.0",
                        "cy_name": f"ext_{suffix}",
                        "categories": [],
                        "config": {},
                    }
                ),
                "SKILL.md": "# Test",
                "Makefile": "all:\n\techo hi",
            }
        )

        resp = await client.post(
            f"/v1/{client._test_tenant}/skills/import",
            files={"file": ("ext.zip", zip_bytes, "application/zip")},
        )
        assert resp.status_code == 422

    async def test_empty_zip_rejected(self, client):
        """Zip with no files should fail (missing required files)."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w"):
            pass  # Empty zip
        zip_bytes = buf.getvalue()

        resp = await client.post(
            f"/v1/{client._test_tenant}/skills/import",
            files={"file": ("empty.zip", zip_bytes, "application/zip")},
        )
        assert resp.status_code == 422
