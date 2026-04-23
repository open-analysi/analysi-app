"""
Security regression tests: actor identity propagation via contextvars (Round 18).

Validates that internal_auth_headers() automatically picks up the actor
from the execution context, so worker code doesn't need to explicitly
thread actor_user_id through every constructor and HTTP call.

Without this, all pipeline HTTP calls run as ``system`` — a privilege
escalation path since system has broader permissions than analyst RBAC.
"""

from unittest.mock import patch
from uuid import uuid4

import pytest

from analysi.common.internal_auth import (
    get_actor_user_id,
    internal_auth_headers,
    set_actor_user_id,
)


@pytest.mark.unit
class TestActorContextPropagation:
    """Verify contextvars-based actor propagation in internal_auth_headers."""

    def test_no_actor_returns_system_only_headers(self):
        """Without actor set, headers contain only the API key."""
        # Reset to no actor
        set_actor_user_id(None)

        with patch.dict("os.environ", {"ANALYSI_SYSTEM_API_KEY": "test-key"}):
            headers = internal_auth_headers()

        assert headers["X-API-Key"] == "test-key"
        assert "X-Actor-User-Id" not in headers

    def test_set_actor_propagates_to_headers(self):
        """After set_actor_user_id(), headers include X-Actor-User-Id."""
        actor_id = str(uuid4())
        set_actor_user_id(actor_id)

        try:
            with patch.dict("os.environ", {"ANALYSI_SYSTEM_API_KEY": "test-key"}):
                headers = internal_auth_headers()

            assert headers["X-API-Key"] == "test-key"
            assert headers["X-Actor-User-Id"] == actor_id
        finally:
            set_actor_user_id(None)

    def test_explicit_param_overrides_context(self):
        """Explicit actor_user_id parameter takes precedence over context."""
        context_actor = str(uuid4())
        explicit_actor = str(uuid4())
        set_actor_user_id(context_actor)

        try:
            headers = internal_auth_headers(actor_user_id=explicit_actor)
            assert headers["X-Actor-User-Id"] == explicit_actor
        finally:
            set_actor_user_id(None)

    def test_get_actor_user_id_reads_context(self):
        """get_actor_user_id() returns value set by set_actor_user_id()."""
        actor_id = str(uuid4())
        set_actor_user_id(actor_id)

        try:
            assert get_actor_user_id() == actor_id
        finally:
            set_actor_user_id(None)

    def test_set_returns_reset_token(self):
        """set_actor_user_id() returns a token that can reset to prior value."""
        original = str(uuid4())
        set_actor_user_id(original)

        override = str(uuid4())
        token = set_actor_user_id(override)
        assert get_actor_user_id() == override

        # Reset using token
        from analysi.common.internal_auth import _actor_user_id_var

        _actor_user_id_var.reset(token)
        assert get_actor_user_id() == original

        # Clean up
        set_actor_user_id(None)


@pytest.mark.unit
class TestClientHeadersProperty:
    """Verify that HTTP clients use fresh headers (not cached at init)."""

    def test_backend_api_client_headers_are_dynamic(self):
        """BackendAPIClient._headers should reflect current actor context."""
        from analysi.alert_analysis.clients import BackendAPIClient

        client = BackendAPIClient()

        # No actor set — should not include X-Actor-User-Id
        set_actor_user_id(None)
        with patch.dict("os.environ", {"ANALYSI_SYSTEM_API_KEY": "k"}):
            headers_before = client._headers
        assert "X-Actor-User-Id" not in headers_before

        # Set actor — same client instance should now include it
        actor_id = str(uuid4())
        set_actor_user_id(actor_id)
        try:
            with patch.dict("os.environ", {"ANALYSI_SYSTEM_API_KEY": "k"}):
                headers_after = client._headers
            assert headers_after["X-Actor-User-Id"] == actor_id
        finally:
            set_actor_user_id(None)

    def test_kea_client_headers_are_dynamic(self):
        """KeaCoordinationClient._headers should reflect current actor context."""
        from analysi.alert_analysis.clients import KeaCoordinationClient

        client = KeaCoordinationClient(base_url="http://localhost:8000")

        set_actor_user_id(None)
        with patch.dict("os.environ", {"ANALYSI_SYSTEM_API_KEY": "k"}):
            assert "X-Actor-User-Id" not in client._headers

        actor_id = str(uuid4())
        set_actor_user_id(actor_id)
        try:
            with patch.dict("os.environ", {"ANALYSI_SYSTEM_API_KEY": "k"}):
                assert client._headers["X-Actor-User-Id"] == actor_id
        finally:
            set_actor_user_id(None)

    def test_task_generation_client_headers_are_dynamic(self):
        """TaskGenerationApiClient._headers should reflect current actor context."""
        from analysi.agentic_orchestration.task_generation_client import (
            TaskGenerationApiClient,
        )

        client = TaskGenerationApiClient(
            api_base_url="http://localhost:8000",
            tenant_id="test",
        )

        set_actor_user_id(None)
        with patch.dict("os.environ", {"ANALYSI_SYSTEM_API_KEY": "k"}):
            assert "X-Actor-User-Id" not in client._headers

        actor_id = str(uuid4())
        set_actor_user_id(actor_id)
        try:
            with patch.dict("os.environ", {"ANALYSI_SYSTEM_API_KEY": "k"}):
                assert client._headers["X-Actor-User-Id"] == actor_id
        finally:
            set_actor_user_id(None)
