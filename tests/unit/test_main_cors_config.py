"""Regression tests for CORS middleware configuration.

The FastAPI app registers a CORSMiddleware with `allow_credentials=True`.
Combining that with wildcard `allow_methods=["*"]` or
`allow_headers=["*"]` broadens the attack surface for cross-origin
requests (any method, any header) without adding functional value. The
app must enumerate the methods and headers it actually uses.
"""

from fastapi.middleware.cors import CORSMiddleware


def _cors_kwargs():
    """Return the kwargs the app passes to CORSMiddleware."""
    from analysi.main import app

    for mw in app.user_middleware:
        if mw.cls is CORSMiddleware:
            return mw.kwargs
    raise AssertionError("CORSMiddleware is not registered on the app")


class TestCorsMiddlewareConfig:
    """The CORS middleware must not use wildcards for methods/headers."""

    def test_allow_methods_is_not_wildcard(self):
        methods = _cors_kwargs()["allow_methods"]
        assert methods != ["*"], "allow_methods=['*'] is too permissive"
        assert "*" not in methods

    def test_allow_methods_covers_common_verbs(self):
        """The app uses GET/POST/PUT/PATCH/DELETE — all must be allowed."""
        methods = set(_cors_kwargs()["allow_methods"])
        assert {"GET", "POST", "PUT", "PATCH", "DELETE"}.issubset(methods)

    def test_allow_headers_is_not_wildcard(self):
        headers = _cors_kwargs()["allow_headers"]
        assert headers != ["*"], "allow_headers=['*'] is too permissive"
        assert "*" not in headers

    def test_allow_headers_covers_auth_and_content_type(self):
        """Headers actually used by clients must be explicitly allowed."""
        headers_lower = {h.lower() for h in _cors_kwargs()["allow_headers"]}
        assert "authorization" in headers_lower
        assert "content-type" in headers_lower
        assert "x-api-key" in headers_lower

    def test_credentials_still_enabled(self):
        """Regression: CORS credentials must remain on for cookie/JWT auth."""
        assert _cors_kwargs()["allow_credentials"] is True
