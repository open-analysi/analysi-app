"""Regression tests for credential decrypt permission escalation.

P0: GET /{tenant}/credentials/{credential_id} returned plaintext secrets
but was only protected by integrations.read (inherited from router scope).
Since viewer role has integrations.read, any low-privilege user could
decrypt all tenant integration credentials.

Fix: Added explicit require_permission("integrations", "update") on the
get_credential endpoint, restricting decrypt to admin+ roles.
"""

import pathlib

import pytest

from analysi.auth.permissions import PERMISSION_MAP


class TestCredentialDecryptPermission:
    """Verify the decrypt endpoint requires elevated permissions."""

    @pytest.fixture
    def source(self):
        path = (
            pathlib.Path(__file__).resolve().parents[3]
            / "src"
            / "analysi"
            / "routers"
            / "credentials.py"
        )
        return path.read_text()

    def test_get_credential_has_explicit_permission_guard(self, source):
        """get_credential endpoint must have its own require_permission dependency.

        The router-level dependency is only integrations.read. The decrypt
        endpoint needs a STRONGER permission at the endpoint level.
        """
        # Find the decorator block for the get_credential endpoint
        # The decorator is multiline: @router.get(\n    "/{credential_id}",\n    ...\n)
        lines = source.splitlines()
        in_decorator = False
        has_permission_dep = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("@router.get("):
                in_decorator = True
                continue
            if (
                in_decorator
                and "credential_id" in stripped
                and "integration" not in stripped
            ):
                # We're in the right decorator block (not the integration one)
                continue
            if in_decorator and "require_permission" in stripped:
                has_permission_dep = True
                break
            if in_decorator and stripped.startswith("async def get_credential"):
                break
        assert has_permission_dep, (
            "get_credential endpoint is missing an explicit require_permission dependency — "
            "it inherits only integrations.read from the router, allowing viewers to decrypt secrets"
        )

    def test_get_credential_requires_integrations_update(self, source):
        """Decrypt endpoint must require integrations.update, not just read."""
        lines = source.splitlines()
        in_get_credential = False
        for i, line in enumerate(lines):
            if "async def get_credential(" in line:
                # Check the decorator block above this function
                # Search backwards from the function definition
                for j in range(i - 1, max(0, i - 10), -1):
                    if "require_permission" in lines[j]:
                        assert '"integrations"' in lines[j], (
                            f"Expected require_permission('integrations', ...), got: {lines[j].strip()}"
                        )
                        assert '"update"' in lines[j], (
                            f"Expected require_permission(..., 'update'), got: {lines[j].strip()}"
                        )
                        in_get_credential = True
                        break
                break
        assert in_get_credential, (
            "Could not find require_permission in get_credential decorator"
        )


class TestRBACViewerCannotDecrypt:
    """Verify viewer role cannot access the decrypt permission."""

    def test_viewer_has_integrations_read(self):
        """Viewer should have integrations.read (for listing metadata)."""
        viewer_perms = PERMISSION_MAP["viewer"]
        assert ("integrations", "read") in viewer_perms

    def test_viewer_does_not_have_integrations_update(self):
        """Viewer must NOT have integrations.update (blocks decrypt access)."""
        viewer_perms = PERMISSION_MAP["viewer"]
        assert ("integrations", "update") not in viewer_perms, (
            "viewer has integrations.update — this would allow credential decryption"
        )

    def test_analyst_does_not_have_integrations_update(self):
        """Analyst must NOT have integrations.update (blocks decrypt access)."""
        analyst_perms = PERMISSION_MAP["analyst"]
        assert ("integrations", "update") not in analyst_perms, (
            "analyst has integrations.update — this would allow credential decryption"
        )

    def test_admin_has_integrations_update(self):
        """Admin SHOULD have integrations.update (can decrypt)."""
        admin_perms = PERMISSION_MAP["admin"]
        assert ("integrations", "update") in admin_perms

    def test_owner_has_integrations_update(self):
        """Owner SHOULD have integrations.update (can decrypt)."""
        owner_perms = PERMISSION_MAP["owner"]
        assert ("integrations", "update") in owner_perms

    def test_system_has_integrations_update(self):
        """System role has integrations.update for last_run_at worker cron updates.

        This is safe because credential decryption is gated by an explicit
        require_permission("integrations", "update") on the REST GET endpoint,
        and workers use internal service calls that don't hit that endpoint.
        """
        system_perms = PERMISSION_MAP["system"]
        assert ("integrations", "update") in system_perms


class TestCredentialListSafety:
    """Verify the list endpoint does NOT return plaintext secrets."""

    @pytest.fixture
    def source(self):
        path = (
            pathlib.Path(__file__).resolve().parents[3]
            / "src"
            / "analysi"
            / "routers"
            / "credentials.py"
        )
        return path.read_text()

    def test_list_endpoint_response_model_is_metadata(self, source):
        """List endpoint must use CredentialMetadata, not CredentialDecrypted."""
        lines = source.splitlines()
        for i, line in enumerate(lines):
            if "async def list_credentials" in line:
                # Check the decorator block above for response_model
                for j in range(i - 1, max(0, i - 10), -1):
                    if "response_model" in lines[j]:
                        assert "CredentialDecrypted" not in lines[j], (
                            "list_credentials response_model should not be CredentialDecrypted"
                        )
                        assert "CredentialMetadata" in lines[j], (
                            "list_credentials response_model should be CredentialMetadata"
                        )
                        return
                break
        pytest.fail("Could not find response_model for list_credentials")
