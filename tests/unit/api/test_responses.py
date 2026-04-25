"""Unit tests for the Sifnos common API response library.

Tests response helpers, pagination params, and envelope structure.
"""

from unittest.mock import MagicMock

from pydantic import BaseModel

from analysi.api.pagination import PaginationParams
from analysi.api.responses import (
    ApiListResponse,
    ApiMeta,
    ApiResponse,
    api_list_response,
    api_response,
)


def _make_request(request_id: str = "test-uuid-1234") -> MagicMock:
    """Create a mock Request with request_id in state."""
    request = MagicMock()
    request.state.request_id = request_id
    return request


def _make_request_no_id() -> MagicMock:
    """Create a mock Request without request_id (simulates missing middleware)."""
    request = MagicMock()
    # Simulate missing attribute — getattr with default should return "unknown"
    del request.state.request_id
    type(request.state).request_id = property(
        lambda self: (_ for _ in ()).throw(AttributeError)
    )
    return request


class SampleModel(BaseModel):
    id: str
    name: str


# ── api_response() ──────────────────────────────────────────────────


class TestApiResponse:
    def test_wraps_pydantic_model(self):
        request = _make_request()
        result = api_response(SampleModel(id="1", name="foo"), request=request)

        assert result.meta.request_id == "test-uuid-1234"
        assert result.data.id == "1"
        assert result.data.name == "foo"

    def test_wraps_dict(self):
        request = _make_request()
        result = api_response({"key": "value"}, request=request)

        assert result.data == {"key": "value"}
        assert result.meta.request_id == "test-uuid-1234"

    def test_fallback_request_id_when_middleware_missing(self):
        request = _make_request_no_id()
        result = api_response({"x": 1}, request=request)

        assert result.meta.request_id == "unknown"

    def test_meta_has_no_pagination_fields(self):
        """Single-item responses should not have pagination metadata."""
        request = _make_request()
        result = api_response({"x": 1}, request=request)

        meta_dict = result.meta.model_dump()
        assert "total" not in meta_dict
        assert "limit" not in meta_dict
        assert "offset" not in meta_dict
        assert "has_next" not in meta_dict


# ── api_list_response() ─────────────────────────────────────────────


class TestApiListResponse:
    def test_with_pagination(self):
        """Paginated list includes limit/offset/has_next in meta."""
        request = _make_request()
        pagination = PaginationParams(limit=10, offset=0)
        items = [SampleModel(id=str(i), name=f"item-{i}") for i in range(10)]

        result = api_list_response(
            items, total=25, request=request, pagination=pagination
        )

        assert len(result.data) == 10
        assert result.meta.total == 25
        assert result.meta.limit == 10
        assert result.meta.offset == 0
        assert result.meta.has_next is True
        assert result.meta.request_id == "test-uuid-1234"

    def test_last_page_has_next_false(self):
        request = _make_request()
        pagination = PaginationParams(limit=10, offset=20)

        result = api_list_response(
            [{"id": "1"}], total=25, request=request, pagination=pagination
        )

        assert result.meta.has_next is False

    def test_without_pagination_batch_lookup(self):
        """Batch lookup (no pagination) — meta has total + request_id only."""
        request = _make_request()
        items = [{"id": "a"}, {"id": "b"}]

        result = api_list_response(items, total=2, request=request)

        assert result.meta.total == 2
        assert result.meta.request_id == "test-uuid-1234"
        # Pagination fields are NOT present when pagination=None
        meta_dict = result.meta.model_dump()
        assert "limit" not in meta_dict
        assert "offset" not in meta_dict
        assert "has_next" not in meta_dict

    def test_empty_list(self):
        request = _make_request()

        result = api_list_response([], total=0, request=request)

        assert result.data == []
        assert result.meta.total == 0


# ── PaginationParams ────────────────────────────────────────────────


class TestPaginationParams:
    def test_defaults(self):
        # When constructed directly (outside FastAPI DI), Query defaults
        # aren't resolved. Use explicit values to test the class contract.
        p = PaginationParams(limit=50, offset=0)
        assert p.limit == 50
        assert p.offset == 0

    def test_custom_values(self):
        p = PaginationParams(limit=20, offset=100)
        assert p.limit == 20
        assert p.offset == 100


# ── Pydantic schema validation ──────────────────────────────────────


class TestSchemaValidation:
    def test_api_response_schema(self):
        """ApiResponse[T] serializes correctly via Pydantic."""
        resp = ApiResponse[SampleModel](
            data=SampleModel(id="1", name="test"),
            meta=ApiMeta(request_id="abc"),
        )
        d = resp.model_dump()
        assert d["data"]["id"] == "1"
        assert d["meta"]["request_id"] == "abc"
        # Optional pagination fields are omitted (not null)
        assert "total" not in d["meta"]

    def test_api_list_response_schema(self):
        resp = ApiListResponse[SampleModel](
            data=[SampleModel(id="1", name="a"), SampleModel(id="2", name="b")],
            meta=ApiMeta(request_id="xyz", total=2),
        )
        d = resp.model_dump()
        assert len(d["data"]) == 2
        assert d["meta"]["total"] == 2
        assert "limit" not in d["meta"]  # not paginated

    def test_api_meta_with_pagination(self):
        meta = ApiMeta(request_id="r1", total=100, limit=20, offset=40, has_next=True)
        d = meta.model_dump()
        assert d["limit"] == 20
        assert d["offset"] == 40
        assert d["has_next"] is True
