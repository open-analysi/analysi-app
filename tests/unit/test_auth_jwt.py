"""Unit tests for JWT validation and JWKS client."""

from unittest.mock import MagicMock, patch

import jwt
import pytest
from fastapi import HTTPException

from analysi.auth import jwks as jwks_module
from analysi.auth.jwks import get_jwks_client, is_jwks_configured
from analysi.auth.jwt import validate_jwt_token
from analysi.auth.models import CurrentUser

_ISSUER = "https://auth.analysi.io/realms/analysi"
_AUDIENCE = "analysi-app"

_VALID_PAYLOAD = {
    "sub": "user-abc",
    "email": "alice@acme.com",
    "tenant_id": "acme",
    "roles": ["analyst"],
    "iss": _ISSUER,
    "aud": _AUDIENCE,
}


# ---------------------------------------------------------------------------
# JWKS client state tests
# ---------------------------------------------------------------------------


class TestJwksClient:
    def setup_method(self):
        jwks_module._jwks_client = None

    def teardown_method(self):
        jwks_module._jwks_client = None

    def test_get_jwks_client_not_initialized_raises(self):
        with pytest.raises(RuntimeError, match="not initialised"):
            get_jwks_client()

    def test_is_jwks_configured_false_when_not_init(self):
        assert is_jwks_configured() is False

    def test_is_jwks_configured_true_after_mock_init(self):
        jwks_module._jwks_client = MagicMock()
        assert is_jwks_configured() is True


# ---------------------------------------------------------------------------
# JWT validation tests
# ---------------------------------------------------------------------------


class TestValidateJwtToken:
    def setup_method(self):
        jwks_module._jwks_client = MagicMock()

    def teardown_method(self):
        jwks_module._jwks_client = None

    def test_validate_valid_token_returns_current_user(self):
        with patch("analysi.auth.jwt.jwt.decode", return_value=_VALID_PAYLOAD):
            result = validate_jwt_token("any.token", audience=_AUDIENCE, issuer=_ISSUER)

        assert isinstance(result, CurrentUser)
        assert result.user_id == "user-abc"
        assert result.email == "alice@acme.com"
        assert result.tenant_id == "acme"
        assert result.actor_type == "user"

    def test_validate_platform_admin_token_no_tenant(self):
        payload = {**_VALID_PAYLOAD, "roles": ["platform_admin"], "tenant_id": None}
        with patch("analysi.auth.jwt.jwt.decode", return_value=payload):
            result = validate_jwt_token("any.token", audience=_AUDIENCE, issuer=_ISSUER)

        assert result.is_platform_admin is True
        assert result.tenant_id is None

    def test_validate_expired_token_raises_401(self):
        with patch(
            "analysi.auth.jwt.jwt.decode",
            side_effect=jwt.ExpiredSignatureError("expired"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                validate_jwt_token("any.token", audience=_AUDIENCE, issuer=_ISSUER)
        assert exc_info.value.status_code == 401

    def test_validate_wrong_audience_raises_401(self):
        with patch(
            "analysi.auth.jwt.jwt.decode",
            side_effect=jwt.InvalidAudienceError("bad aud"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                validate_jwt_token("any.token", audience=_AUDIENCE, issuer=_ISSUER)
        assert exc_info.value.status_code == 401

    def test_validate_wrong_issuer_raises_401(self):
        with patch(
            "analysi.auth.jwt.jwt.decode",
            side_effect=jwt.InvalidIssuerError("bad iss"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                validate_jwt_token("any.token", audience=_AUDIENCE, issuer=_ISSUER)
        assert exc_info.value.status_code == 401

    def test_validate_tampered_signature_raises_401(self):
        with patch(
            "analysi.auth.jwt.jwt.decode",
            side_effect=jwt.InvalidSignatureError("bad sig"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                validate_jwt_token("any.token", audience=_AUDIENCE, issuer=_ISSUER)
        assert exc_info.value.status_code == 401

    def test_validate_generic_invalid_token_raises_401(self):
        with patch(
            "analysi.auth.jwt.jwt.decode",
            side_effect=jwt.InvalidTokenError("generic"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                validate_jwt_token("any.token", audience=_AUDIENCE, issuer=_ISSUER)
        assert exc_info.value.status_code == 401

    def test_validate_when_jwks_not_configured_raises_401(self):
        jwks_module._jwks_client = None
        with pytest.raises(HTTPException) as exc_info:
            validate_jwt_token("any.token", audience=_AUDIENCE, issuer=_ISSUER)
        assert exc_info.value.status_code == 401

    def test_validate_token_missing_tenant_id_claim(self):
        """JWT without tenant_id claim → CurrentUser.tenant_id is None."""
        payload = {k: v for k, v in _VALID_PAYLOAD.items() if k != "tenant_id"}
        with patch("analysi.auth.jwt.jwt.decode", return_value=payload):
            result = validate_jwt_token("any.token", audience=_AUDIENCE, issuer=_ISSUER)
        assert result.tenant_id is None
