"""Unit tests for CurrentUser dataclass."""

import pytest

from analysi.auth.models import CurrentUser


class TestCurrentUserIsplatformAdmin:
    def test_is_platform_admin_true(self):
        user = CurrentUser(
            user_id="u1",
            email="admin@analysi.io",
            tenant_id=None,
            roles=["platform_admin"],
            actor_type="user",
        )
        assert user.is_platform_admin is True

    def test_is_platform_admin_false(self):
        user = CurrentUser(
            user_id="u2",
            email="alice@acme.com",
            tenant_id="acme",
            roles=["analyst"],
            actor_type="user",
        )
        assert user.is_platform_admin is False

    def test_is_platform_admin_multi_role(self):
        user = CurrentUser(
            user_id="u3",
            email="alice@acme.com",
            tenant_id="acme",
            roles=["analyst", "platform_admin"],
            actor_type="user",
        )
        assert user.is_platform_admin is True

    def test_is_platform_admin_empty_roles(self):
        user = CurrentUser(
            user_id="u4",
            email="bob@acme.com",
            tenant_id="acme",
            roles=[],
            actor_type="user",
        )
        assert user.is_platform_admin is False

    def test_actor_type_defaults_to_user(self):
        user = CurrentUser(
            user_id="u5",
            email="bob@acme.com",
            tenant_id="acme",
            roles=["owner"],
        )
        assert user.actor_type == "user"

    def test_tenant_id_none_for_platform_admin(self):
        user = CurrentUser(
            user_id="u6",
            email="admin@analysi.io",
            tenant_id=None,
            roles=["platform_admin"],
            actor_type="user",
        )
        assert user.tenant_id is None

    @pytest.mark.parametrize("actor_type", ["user", "api_key", "system"])
    def test_valid_actor_types(self, actor_type):
        user = CurrentUser(
            user_id="u7",
            email="x@y.com",
            tenant_id="t1",
            roles=["analyst"],
            actor_type=actor_type,
        )
        assert user.actor_type == actor_type
