"""Integration tests for the task-assist autocomplete endpoint."""

import os
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.db.session import get_db
from analysi.main import app


@pytest.mark.asyncio
@pytest.mark.integration
class TestCyAutocomplete:
    """Tests for POST /{tenant}/tasks/autocomplete."""

    @pytest.fixture
    async def client(self, integration_test_session) -> AsyncGenerator[AsyncClient]:
        """Async HTTP client wired to the test database."""

        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c

        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # Happy-path: LLM returns valid JSON completions
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_autocomplete_returns_completions(self, client: AsyncClient):
        """Endpoint returns completions when LLM responds with valid JSON."""
        fake_completions = [
            {
                "insert_text": "un(prompt=",
                "label": "llm_run(prompt=...",
                "detail": "Run LLM with a prompt",
                "kind": "function",
            }
        ]

        # Patch the service function so we don't make real LLM calls
        with (
            patch(
                "analysi.routers.task_assist.get_cy_completions",
                new=AsyncMock(return_value=fake_completions),
            ),
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}),
        ):
            response = await client.post(
                "/v1/test-tenant/tasks/autocomplete",
                json={
                    "script_prefix": "alert = input.alert ?? {}\nresult = llm_r",
                    "trigger_kind": "character",
                    "trigger_character": "r",
                },
            )

        assert response.status_code == 200
        data = response.json()["data"]
        assert "completions" in data
        assert len(data["completions"]) == 1
        item = data["completions"][0]
        assert item["insert_text"] == "un(prompt="
        assert item["label"] == "llm_run(prompt=..."
        assert item["kind"] == "function"

    @pytest.mark.asyncio
    async def test_autocomplete_empty_prefix(self, client: AsyncClient):
        """Endpoint accepts an empty script prefix."""
        with patch(
            "analysi.routers.task_assist.get_cy_completions",
            new=AsyncMock(return_value=[]),
        ):
            response = await client.post(
                "/v1/test-tenant/tasks/autocomplete",
                json={"script_prefix": "", "trigger_kind": "invoked"},
            )

        assert response.status_code == 200
        assert response.json()["data"]["completions"] == []

    @pytest.mark.asyncio
    async def test_autocomplete_with_suffix(self, client: AsyncClient):
        """Endpoint accepts script_suffix and trigger_character."""
        fake_completions = [
            {
                "insert_text": "title",
                "label": ".title",
                "detail": "Alert title field",
                "kind": "field",
            }
        ]

        with patch(
            "analysi.routers.task_assist.get_cy_completions",
            new=AsyncMock(return_value=fake_completions),
        ):
            response = await client.post(
                "/v1/test-tenant/tasks/autocomplete",
                json={
                    "script_prefix": "alert = input.alert ?? {}\nx = alert.",
                    "script_suffix": "\noutput.result = x",
                    "trigger_kind": "character",
                    "trigger_character": ".",
                },
            )

        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data["completions"]) == 1
        assert data["completions"][0]["kind"] == "field"

    # ------------------------------------------------------------------
    # Keyword fast-path (no LLM call, hardcoded Cy snippets)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_for_keyword_returns_cy_syntax(self, client: AsyncClient):
        """Typing 'for' returns Cy-style 'for (item in items) { }', not Python."""
        response = await client.post(
            "/v1/test-tenant/tasks/autocomplete",
            json={
                "script_prefix": "fo",
                "trigger_kind": "character",
                "trigger_character": "r",
            },
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data["completions"]) >= 1
        item = data["completions"][0]
        # insert_text must contain Cy-style parentheses, not Python colon
        assert "(" in item["insert_text"]
        assert ":" not in item["insert_text"]
        assert item["kind"] == "keyword"

    @pytest.mark.asyncio
    async def test_if_keyword_returns_cy_syntax(self, client: AsyncClient):
        """Typing 'if' returns Cy-style 'if (condition) { }', not Python."""
        response = await client.post(
            "/v1/test-tenant/tasks/autocomplete",
            json={
                "script_prefix": "i",
                "trigger_kind": "character",
                "trigger_character": "f",
            },
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data["completions"]) >= 1
        item = data["completions"][0]
        assert "(condition)" in item["insert_text"]
        assert "{" in item["insert_text"]
        assert item["kind"] == "keyword"

    @pytest.mark.asyncio
    async def test_while_keyword_returns_cy_syntax(self, client: AsyncClient):
        """Typing 'while' returns Cy-style 'while (condition) { }'."""
        response = await client.post(
            "/v1/test-tenant/tasks/autocomplete",
            json={
                "script_prefix": "whil",
                "trigger_kind": "character",
                "trigger_character": "e",
            },
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data["completions"]) >= 1
        assert data["completions"][0]["kind"] == "keyword"

    @pytest.mark.asyncio
    async def test_for_open_paren_suppresses_completions(self, client: AsyncClient):
        """Typing 'for(' suppresses completions to avoid extra ')' from editor auto-close."""
        response = await client.post(
            "/v1/test-tenant/tasks/autocomplete",
            json={
                # cursor is between ( and ) — prefix ends with '('
                "script_prefix": "for(",
                "script_suffix": ")",
                "trigger_kind": "invoked",
            },
        )

        assert response.status_code == 200
        # No completions: any insert_text would produce an extra ')' from the suffix
        assert response.json()["data"]["completions"] == []

    @pytest.mark.asyncio
    async def test_non_keyword_falls_through_to_llm(self, client: AsyncClient):
        """Non-keyword prefix still goes through LLM (mocked here)."""
        fake_completions = [
            {
                "insert_text": "un(prompt=",
                "label": "llm_run",
                "detail": "",
                "kind": "function",
            }
        ]
        with patch(
            "analysi.routers.task_assist.get_cy_completions",
            new=AsyncMock(return_value=fake_completions),
        ):
            response = await client.post(
                "/v1/test-tenant/tasks/autocomplete",
                json={
                    "script_prefix": "llm_r",
                    "trigger_kind": "character",
                    "trigger_character": "u",
                },
            )

        assert response.status_code == 200
        assert response.json()["data"]["completions"][0]["kind"] == "function"

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_autocomplete_no_llm_configured_returns_422(
        self, client: AsyncClient
    ):
        """Endpoint returns 422 when no LLM is configured."""
        with patch(
            "analysi.routers.task_assist.get_cy_completions",
            new=AsyncMock(side_effect=ValueError("No LLM integrations configured")),
        ):
            response = await client.post(
                "/v1/test-tenant/tasks/autocomplete",
                json={"script_prefix": "x = ", "trigger_kind": "invoked"},
            )

        assert response.status_code == 422

    # ------------------------------------------------------------------
    # Regression: keyword fast-path with trailing space
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_if_with_trailing_space_returns_cy_syntax(self, client: AsyncClient):
        """Regression: 'if ' (space trigger) must still return Cy syntax, not Python.

        Previously the fast-path regex r'[\\w]+$' didn't match when the prefix
        ended with whitespace, so the request fell through to the LLM which
        generated Python-style 'True:' completions.
        """
        response = await client.post(
            "/v1/test-tenant/tasks/autocomplete",
            json={
                "script_prefix": "i=[1,2,3]\n\nif ",
                "trigger_kind": "character",
                "trigger_character": " ",
            },
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data["completions"]) >= 1
        for item in data["completions"]:
            # Every suggestion must use Cy block syntax, not Python colon syntax
            assert ":" not in item["insert_text"], (
                f"Got Python-style colon in completion: {item['insert_text']!r}"
            )
            assert "(" in item["insert_text"]
            assert item["kind"] == "keyword"

    # ------------------------------------------------------------------
    # Regression: cursor inside string literal
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_cursor_inside_string_suppresses_completions(
        self, client: AsyncClient
    ):
        """Regression: cursor inside an open string literal returns no completions.

        Previously the LLM would inject the golden example task template as
        string content when triggered with an unclosed double-quote prefix.
        """
        response = await client.post(
            "/v1/test-tenant/tasks/autocomplete",
            json={
                "script_prefix": 'i=[1,2,3]\n\nif (i[0] == 1) {\n    return "',
                "script_suffix": '"\n}\n\nreturn "Hello World"',
                "trigger_kind": "invoked",
            },
        )

        assert response.status_code == 200
        assert response.json()["data"]["completions"] == [], (
            "Expected no completions inside an open string literal"
        )

    @pytest.mark.asyncio
    async def test_cursor_after_closed_string_allows_completions(
        self, client: AsyncClient
    ):
        """Closed strings on the same line don't suppress completions."""
        fake_completions = [
            {"insert_text": "True", "label": "True", "detail": "", "kind": "keyword"}
        ]
        with patch(
            "analysi.routers.task_assist.get_cy_completions",
            new=AsyncMock(return_value=fake_completions),
        ):
            response = await client.post(
                "/v1/test-tenant/tasks/autocomplete",
                json={
                    # Two closed strings on the line — cursor is outside any string
                    "script_prefix": 'x = "hello"\ny = "world"\nz = ',
                    "trigger_kind": "invoked",
                },
            )

        assert response.status_code == 200
        assert len(response.json()["data"]["completions"]) == 1

    @pytest.mark.asyncio
    async def test_autocomplete_service_error_returns_500(self, client: AsyncClient):
        """Endpoint returns 500 on unexpected service errors."""
        with patch(
            "analysi.routers.task_assist.get_cy_completions",
            new=AsyncMock(side_effect=RuntimeError("unexpected")),
        ):
            response = await client.post(
                "/v1/test-tenant/tasks/autocomplete",
                json={"script_prefix": "x = ", "trigger_kind": "invoked"},
            )

        assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_autocomplete_invalid_trigger_kind_returns_422(
        self, client: AsyncClient
    ):
        """Endpoint validates trigger_kind enum values."""
        response = await client.post(
            "/v1/test-tenant/tasks/autocomplete",
            json={"script_prefix": "x = ", "trigger_kind": "bogus"},
        )
        assert response.status_code == 422
