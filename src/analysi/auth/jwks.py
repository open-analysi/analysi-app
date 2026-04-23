"""JWKS client — fetches and caches Keycloak public keys.

Usage:
    # At startup (fail-fast):
    await initialize_jwks_client(settings.ANALYSI_AUTH_JWKS_URI)

    # In JWT validation:
    client = get_jwks_client()
    signing_key = client.get_signing_key_from_jwt(token)
"""

from jwt import PyJWKClient

from analysi.config.logging import get_logger

logger = get_logger(__name__)

_jwks_client: PyJWKClient | None = None

# Cache TTL in seconds (5 minutes — matches access token lifetime)
_JWKS_CACHE_TTL = 300


def initialize_jwks_client(jwks_uri: str) -> None:
    """Fetch JWKS once at startup and initialise the singleton.

    Raises RuntimeError if the JWKS endpoint is unreachable so the server
    refuses to start rather than silently operating without key material.
    """
    global _jwks_client
    client = PyJWKClient(
        jwks_uri,
        cache_jwk_set=True,
        lifespan=_JWKS_CACHE_TTL,
        timeout=30,
    )
    # Eagerly fetch keys — raises PyJWKClientConnectionError if unreachable
    client.get_jwk_set(refresh=True)
    _jwks_client = client
    logger.info("jwks_client_initialized", jwks_uri=jwks_uri)


def get_jwks_client() -> PyJWKClient:
    """Return the initialised JWKS client singleton.

    Raises RuntimeError if ``initialize_jwks_client`` was never called.
    """
    if _jwks_client is None:
        raise RuntimeError(
            "JWKS client is not initialised. "
            "Call initialize_jwks_client() at application startup."
        )
    return _jwks_client


def is_jwks_configured() -> bool:
    """True when the JWKS client has been initialised."""
    return _jwks_client is not None
