"""Unit tests for RFC 9457 error handling.

Verifies that all error responses:
1. Have Content-Type: application/problem+json
2. Include request_id extension field
3. Follow RFC 9457 structure (type, title, status, detail)
"""

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import SQLAlchemyError

from analysi.api import RequestIdMiddleware, init_error_handling


@pytest.fixture
def app():
    """App with error handling + RequestIdMiddleware."""
    app = FastAPI()
    init_error_handling(app)
    app.add_middleware(RequestIdMiddleware)

    @app.get("/ok")
    async def ok():
        return {"status": "ok"}

    @app.get("/http-error")
    async def http_error():
        raise HTTPException(status_code=404, detail="Thing not found")

    @app.get("/http-error-structured")
    async def http_error_structured():
        raise HTTPException(
            status_code=409,
            detail={"error": "conflict", "workflows": ["wf-1", "wf-2"]},
        )

    @app.get("/http-error-with-headers")
    async def http_error_with_headers():
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.get("/validation-error")
    async def validation_error(required_param: int):
        return {}  # never reached — param missing triggers validation

    @app.get("/db-error")
    async def db_error():
        raise SQLAlchemyError("connection refused at 10.0.1.5:5432 user=secret")

    @app.get("/unhandled")
    async def unhandled():
        raise RuntimeError("something broke")

    return app


class TestHttpExceptionHandler:
    @pytest.mark.asyncio
    async def test_404_returns_rfc9457(self, app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/http-error")

        assert resp.status_code == 404
        assert "application/problem+json" in resp.headers["content-type"]
        body = resp.json()
        assert body["status"] == 404
        assert body["detail"] == "Thing not found"
        assert "request_id" in body

    @pytest.mark.asyncio
    async def test_structured_detail_preserved(self, app):
        """HTTPException(detail={...}) keeps structured data in detail_data."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/http-error-structured")

        assert resp.status_code == 409
        body = resp.json()
        # detail is a human-readable string, not a stringified dict
        assert isinstance(body["detail"], str)
        assert "'" not in body["detail"]  # not Python repr
        # Structured data preserved as detail_data
        assert body["detail_data"]["error"] == "conflict"
        assert body["detail_data"]["workflows"] == ["wf-1", "wf-2"]
        assert "request_id" in body

    @pytest.mark.asyncio
    async def test_preserves_exception_headers(self, app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/http-error-with-headers")

        assert resp.status_code == 401
        assert resp.headers.get("www-authenticate") == "Bearer"


class TestValidationErrorHandler:
    @pytest.mark.asyncio
    async def test_422_returns_rfc9457_with_errors(self, app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/validation-error")

        assert resp.status_code == 422
        assert "application/problem+json" in resp.headers["content-type"]
        body = resp.json()
        assert body["detail"] == "Request validation failed"
        assert "request_id" in body
        assert "errors" in body
        assert len(body["errors"]) > 0


class TestSqlAlchemyErrorHandler:
    @pytest.mark.asyncio
    async def test_503_scrubs_db_internals(self, app):
        """SQLAlchemy errors return 503 without leaking connection details."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/db-error")

        assert resp.status_code == 503
        assert "application/problem+json" in resp.headers["content-type"]
        body = resp.json()
        assert body["detail"] == "Database temporarily unavailable. Please retry."
        assert "request_id" in body
        # Must NOT leak DB internals
        assert "10.0.1.5" not in str(body)
        assert "secret" not in str(body)

    @pytest.mark.asyncio
    async def test_request_id_matches_header(self, app):
        """request_id in error body matches X-Request-Id header."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/db-error")

        body = resp.json()
        assert body["request_id"] == resp.headers["x-request-id"]


class TestGenericExceptionHandler:
    @pytest.mark.asyncio
    async def test_500_for_unhandled_exceptions(self, app):
        # raise_app_exceptions=False: httpx re-raises by default even though
        # Starlette's ServerErrorMiddleware handles the exception. Disabling
        # lets us inspect the actual 500 response produced by our handler.
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/unhandled")

        assert resp.status_code == 500
        assert "application/problem+json" in resp.headers["content-type"]
        body = resp.json()
        assert body["detail"] == "Internal server error"
        assert "request_id" in body
        # Must NOT leak exception message
        assert "something broke" not in str(body)
