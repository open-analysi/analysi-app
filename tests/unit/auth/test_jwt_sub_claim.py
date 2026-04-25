"""Unit tests for JWT sub claim validation.

Security: A JWT without a ``sub`` claim must be rejected at the auth
boundary.  An empty ``sub`` could match a DB user with an empty
``keycloak_id``, causing silent privilege escalation (any JWT user
inherits the matched user's owner role).
"""

import pytest
from fastapi import HTTPException

from analysi.auth.jwt import _build_current_user


class TestBuildCurrentUserSubClaim:
    """_build_current_user must reject JWTs missing or empty sub."""

    def test_missing_sub_raises_401(self):
        payload = {
            "email": "attacker@attacker.example",
            "tenant_id": "default",
            "roles": ["admin"],
        }
        with pytest.raises(HTTPException) as exc_info:
            _build_current_user(payload)
        assert exc_info.value.status_code == 401
        assert "missing subject" in exc_info.value.detail

    def test_empty_string_sub_raises_401(self):
        payload = {
            "sub": "",
            "email": "attacker@attacker.example",
            "tenant_id": "default",
            "roles": ["admin"],
        }
        with pytest.raises(HTTPException) as exc_info:
            _build_current_user(payload)
        assert exc_info.value.status_code == 401
        assert "missing subject" in exc_info.value.detail

    def test_whitespace_only_sub_raises_401(self):
        payload = {
            "sub": "   ",
            "email": "attacker@attacker.example",
            "tenant_id": "default",
            "roles": ["admin"],
        }
        with pytest.raises(HTTPException) as exc_info:
            _build_current_user(payload)
        assert exc_info.value.status_code == 401

    def test_none_sub_raises_401(self):
        payload = {
            "sub": None,
            "email": "attacker@attacker.example",
            "tenant_id": "default",
            "roles": ["admin"],
        }
        with pytest.raises(HTTPException) as exc_info:
            _build_current_user(payload)
        assert exc_info.value.status_code == 401

    def test_valid_sub_returns_current_user(self):
        payload = {
            "sub": "abc-123-keycloak-id",
            "email": "user@example.com",
            "tenant_id": "default",
            "roles": ["admin"],
        }
        user = _build_current_user(payload)
        assert user.user_id == "abc-123-keycloak-id"
        assert user.email == "user@example.com"
        assert user.tenant_id == "default"
        assert user.roles == ["admin"]
        assert user.actor_type == "user"

    def test_valid_uuid_sub_returns_current_user(self):
        """Keycloak typically uses UUID format for sub."""
        payload = {
            "sub": "d3bc155a-7ca3-4c1c-b3ff-7b203127bf36",
            "email": "user@example.com",
            "roles": ["viewer"],
        }
        user = _build_current_user(payload)
        assert user.user_id == "d3bc155a-7ca3-4c1c-b3ff-7b203127bf36"

    def test_platform_admin_without_tenant(self):
        """Platform admin JWTs have no tenant_id — must still require sub."""
        payload = {
            "sub": "platform-admin-id",
            "email": "platform@analysi.local",
            "roles": ["platform_admin"],
        }
        user = _build_current_user(payload)
        assert user.user_id == "platform-admin-id"
        assert user.tenant_id is None
