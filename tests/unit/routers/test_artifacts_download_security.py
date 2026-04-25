"""Security tests for the artifact download endpoint.

The artifact filename flows from user-supplied content into the
Content-Disposition HTTP header. An attacker who can control the
filename (via artifact creation) could inject CRLF to split the
response and forge additional headers, or break clients that parse
the header naively. The response must always produce a safe header.
"""

from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from analysi.auth.dependencies import require_current_user
from analysi.auth.models import CurrentUser
from analysi.dependencies.tenant import get_tenant_id
from analysi.routers.artifacts import get_artifact_service, router


def _platform_admin() -> CurrentUser:
    """Platform admin bypasses all permission checks."""
    return CurrentUser(
        user_id="test",
        email="test@test.local",
        tenant_id="t1",
        roles=["platform_admin"],
        actor_type="user",
    )


def _tenant_id() -> str:
    return "t1"


@pytest.fixture
def app_with_mocked_artifact(request):
    """FastAPI app with a mock ArtifactService returning the parametrized filename.

    The test supplies the filename via `request.param`. The service returns
    (content_bytes, mime_type, filename, sha256_hex).
    """
    filename = request.param

    mock_service = AsyncMock()
    mock_service.get_artifact_content = AsyncMock(
        return_value=(
            b"payload-bytes",
            "application/octet-stream",
            filename,
            "deadbeef",
        )
    )

    app = FastAPI()
    app.include_router(router, prefix="/v1")
    # require_permission is a factory — override the inner require_current_user
    # instead (platform_admin bypasses tenant & role checks).
    app.dependency_overrides[require_current_user] = _platform_admin
    app.dependency_overrides[get_tenant_id] = _tenant_id
    app.dependency_overrides[get_artifact_service] = lambda: mock_service

    return app


ARTIFACT_ID = UUID("00000000-0000-0000-0000-000000000001")


class TestContentDispositionHeaderInjection:
    """Content-Disposition must be safe regardless of the stored filename."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "app_with_mocked_artifact",
        ['evil"\r\nX-Injected: owned\r\n\r\n<script>alert(1)</script>'],
        indirect=True,
    )
    async def test_crlf_in_filename_does_not_split_response(
        self, app_with_mocked_artifact
    ):
        """A filename containing CRLF must not inject new headers."""
        transport = ASGITransport(app=app_with_mocked_artifact)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/v1/t1/artifacts/{ARTIFACT_ID}/download")

        assert response.status_code == 200
        disposition = response.headers["content-disposition"]
        # The crucial invariant: no raw CR or LF in the header value.
        assert "\r" not in disposition
        assert "\n" not in disposition
        # The injected header must not appear as a real response header.
        assert "x-injected" not in response.headers

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "app_with_mocked_artifact",
        ['file"name.txt'],
        indirect=True,
    )
    async def test_unescaped_quote_in_filename_is_safe(self, app_with_mocked_artifact):
        """A raw double-quote must not break out of the filename parameter."""
        transport = ASGITransport(app=app_with_mocked_artifact)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/v1/t1/artifacts/{ARTIFACT_ID}/download")

        assert response.status_code == 200
        disposition = response.headers["content-disposition"]
        # Naive f'filename="{name}"' would produce: filename="file"name.txt"
        # — three quotes. A safe encoding must not leave an unbalanced quote
        # that lets a value bleed into a new header parameter.
        quote_count = disposition.count('"')
        assert quote_count == 0 or quote_count % 2 == 0, (
            f"Unbalanced quotes in Content-Disposition: {disposition!r}"
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "app_with_mocked_artifact",
        ["résumé.pdf"],
        indirect=True,
    )
    async def test_unicode_filename_is_properly_encoded(self, app_with_mocked_artifact):
        """Non-ASCII filenames must be encoded per RFC 5987 so clients see
        the correct name (e.g. filename*=UTF-8''r%C3%A9sum%C3%A9.pdf)."""
        transport = ASGITransport(app=app_with_mocked_artifact)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/v1/t1/artifacts/{ARTIFACT_ID}/download")

        assert response.status_code == 200
        disposition = response.headers["content-disposition"]
        # RFC 5987 encoded parameter must be present for non-ASCII names.
        assert "filename*=UTF-8''" in disposition
        # And the percent-encoding of é is %C3%A9.
        assert "r%C3%A9sum%C3%A9.pdf" in disposition

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "app_with_mocked_artifact",
        ["report.pdf"],
        indirect=True,
    )
    async def test_plain_ascii_filename_still_works(self, app_with_mocked_artifact):
        """Regression: normal ASCII filenames must still be represented."""
        transport = ASGITransport(app=app_with_mocked_artifact)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/v1/t1/artifacts/{ARTIFACT_ID}/download")

        assert response.status_code == 200
        disposition = response.headers["content-disposition"]
        assert "attachment" in disposition
        assert "report.pdf" in disposition
