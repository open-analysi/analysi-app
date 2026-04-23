"""JWT validation — verifies Keycloak-issued access tokens.

Always uses RS256 (hardcoded) and validates iss + aud claims.
"""

import jwt
from fastapi import HTTPException

from analysi.auth.jwks import get_jwks_client, is_jwks_configured
from analysi.auth.models import CurrentUser
from analysi.config.logging import get_logger

logger = get_logger(__name__)

# Algorithm pinned — never derive from the token header (algorithm confusion attack)
_ALGORITHMS = ["RS256"]

# Acceptable clock skew between Keycloak and FastAPI containers (seconds)
_LEEWAY = 5


def validate_jwt_token(
    token: str,
    audience: str,
    issuer: str,
) -> CurrentUser:
    """Validate a JWT access token and return a resolved CurrentUser.

    Args:
        token: Raw Bearer token string.
        audience: Expected ``aud`` claim (e.g. ``"analysi-app"``).
        issuer: Expected ``iss`` claim (e.g. ``"https://auth.analysi.io/realms/analysi"``).

    Returns:
        Populated CurrentUser.

    Raises:
        HTTPException(401): On any validation failure.
        RuntimeError: If JWKS is not initialised.
    """
    if not is_jwks_configured():
        raise HTTPException(status_code=401, detail="Auth not configured")

    jwks_client = get_jwks_client()

    try:
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=_ALGORITHMS,
            audience=audience,
            issuer=issuer,
            leeway=_LEEWAY,
        )
    except jwt.ExpiredSignatureError:
        logger.info("jwt_expired")
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidAudienceError:
        logger.warning("jwt_invalid_audience")
        raise HTTPException(status_code=401, detail="Invalid token audience")
    except jwt.InvalidIssuerError:
        logger.warning("jwt_invalid_issuer")
        raise HTTPException(status_code=401, detail="Invalid token issuer")
    except jwt.InvalidSignatureError:
        logger.warning("jwt_invalid_signature")
        raise HTTPException(status_code=401, detail="Invalid token signature")
    except jwt.InvalidTokenError as exc:
        logger.warning("jwt_invalid_token", error=str(exc))
        raise HTTPException(status_code=401, detail="Invalid token")

    return _build_current_user(payload)


def _build_current_user(payload: dict) -> CurrentUser:
    """Parse a validated JWT payload into a CurrentUser.

    Rejects tokens missing the ``sub`` claim — a JWT without ``sub`` cannot
    be tied to a specific identity. Without this check, an empty ``sub``
    could match a DB user with an empty ``keycloak_id``, causing silent
    privilege escalation.
    """
    sub = (payload.get("sub") or "").strip()
    if not sub:
        logger.warning("jwt_missing_sub_claim")
        raise HTTPException(status_code=401, detail="Invalid token: missing subject")

    return CurrentUser(
        user_id=sub,
        email=payload.get("email", ""),
        tenant_id=payload.get("tenant_id"),  # None for platform_admin
        roles=payload.get("roles", []),
        actor_type="user",
    )
