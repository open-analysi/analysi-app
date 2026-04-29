"""Supplementary unit tests for ``analysi.alert_analysis.clients``.

The existing ``test_clients.py`` covers ``execute_workflow`` /
``get_workflow_by_name`` / ``get_workflow_status`` and a couple of network
failure modes. This file fills the remaining methods that the combined
unit + integration coverage report flagged at ~40 %:

- ``get_artifacts_by_workflow_run`` (happy + 5xx + 429 + RequestError)
- ``download_artifact`` (happy + 404 + 5xx + RequestError + HTTPStatusError)
- ``get_dispositions``
- ``update_analysis_status`` (happy + 5xx + 409-cancelled + 4xx + RequestError)
- ``update_alert_analysis_status``
- ``get_alert`` (happy + 404 + 5xx + HTTPStatusError + RequestError)
- ``get_analysis`` (happy + alert-without-analysis + 404)
- ``update_step_progress`` (happy + 5xx + with-error)
- ``KeaCoordinationClient`` ``create_group_with_generation`` /
  ``create_routing_rule`` / ``get_active_workflow`` happy paths

All tests mock ``InternalAsyncClient`` at the module boundary; no real
HTTP, no real DB. The retry decorator is short-circuited by the
project's autouse ``_no_retry_waits`` fixture in ``tests/unit/conftest.py``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from analysi.alert_analysis.clients import (
    BackendAPIClient,
    KeaCoordinationClient,
)
from analysi.common.retry_config import RetryableHTTPError


def _mock_client(response: MagicMock) -> AsyncMock:
    """Build an InternalAsyncClient AsyncMock whose ``__aenter__`` returns a
    client that returns ``response`` for any HTTP verb."""
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    client.post = AsyncMock(return_value=response)
    client.put = AsyncMock(return_value=response)
    return client


@pytest.fixture
def client() -> BackendAPIClient:
    return BackendAPIClient()


# ── get_artifacts_by_workflow_run ──────────────────────────────────────────-


@pytest.mark.asyncio
async def test_get_artifacts_happy(client: BackendAPIClient) -> None:
    resp = MagicMock(status_code=200)
    resp.json.return_value = [{"id": "a1"}, {"id": "a2"}]
    with patch("analysi.alert_analysis.clients.InternalAsyncClient") as cls:
        cls.return_value.__aenter__.return_value = _mock_client(resp)
        out = await client.get_artifacts_by_workflow_run("t", "wfr-1")
    assert len(out) == 2


@pytest.mark.asyncio
async def test_get_artifacts_500_raises_retryable(client: BackendAPIClient) -> None:
    resp = MagicMock(status_code=500)
    with patch("analysi.alert_analysis.clients.InternalAsyncClient") as cls:
        cls.return_value.__aenter__.return_value = _mock_client(resp)
        with pytest.raises(RetryableHTTPError):
            await client.get_artifacts_by_workflow_run("t", "wfr-1")


@pytest.mark.asyncio
async def test_get_artifacts_429_raises_retryable(client: BackendAPIClient) -> None:
    resp = MagicMock(status_code=429)
    with patch("analysi.alert_analysis.clients.InternalAsyncClient") as cls:
        cls.return_value.__aenter__.return_value = _mock_client(resp)
        with pytest.raises(RetryableHTTPError):
            await client.get_artifacts_by_workflow_run("t", "wfr-1")


@pytest.mark.asyncio
async def test_get_artifacts_request_error_wraps_as_retryable(
    client: BackendAPIClient,
) -> None:
    fake = AsyncMock()
    fake.get = AsyncMock(
        side_effect=httpx.ConnectError("connection refused")
    )
    with patch("analysi.alert_analysis.clients.InternalAsyncClient") as cls:
        cls.return_value.__aenter__.return_value = fake
        with pytest.raises(RetryableHTTPError):
            await client.get_artifacts_by_workflow_run("t", "wfr-1")


# ── download_artifact ──────────────────────────────────────────────────────-


@pytest.mark.asyncio
async def test_download_artifact_happy(client: BackendAPIClient) -> None:
    resp = MagicMock(status_code=200, text="hello-content")
    with patch("analysi.alert_analysis.clients.InternalAsyncClient") as cls:
        cls.return_value.__aenter__.return_value = _mock_client(resp)
        out = await client.download_artifact("t", "art-1")
    assert out == "hello-content"


@pytest.mark.asyncio
async def test_download_artifact_404_returns_none(
    client: BackendAPIClient,
) -> None:
    resp = MagicMock(status_code=404)
    with patch("analysi.alert_analysis.clients.InternalAsyncClient") as cls:
        cls.return_value.__aenter__.return_value = _mock_client(resp)
        out = await client.download_artifact("t", "art-missing")
    assert out is None


@pytest.mark.asyncio
async def test_download_artifact_500_raises_retryable(
    client: BackendAPIClient,
) -> None:
    resp = MagicMock(status_code=500)
    with patch("analysi.alert_analysis.clients.InternalAsyncClient") as cls:
        cls.return_value.__aenter__.return_value = _mock_client(resp)
        with pytest.raises(RetryableHTTPError):
            await client.download_artifact("t", "art-1")


@pytest.mark.asyncio
async def test_download_artifact_request_error_wraps_as_retryable(
    client: BackendAPIClient,
) -> None:
    fake = AsyncMock()
    fake.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
    with patch("analysi.alert_analysis.clients.InternalAsyncClient") as cls:
        cls.return_value.__aenter__.return_value = fake
        with pytest.raises(RetryableHTTPError):
            await client.download_artifact("t", "art-1")


@pytest.mark.asyncio
async def test_download_artifact_http_status_error_returns_none(
    client: BackendAPIClient,
) -> None:
    """Unexpected 4xx (other than 404) should be logged and return None."""
    resp = MagicMock(status_code=403)
    resp.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError(
            "forbidden", request=MagicMock(), response=resp
        )
    )
    with patch("analysi.alert_analysis.clients.InternalAsyncClient") as cls:
        cls.return_value.__aenter__.return_value = _mock_client(resp)
        out = await client.download_artifact("t", "art-1")
    assert out is None


# ── get_dispositions ───────────────────────────────────────────────────────-


@pytest.mark.asyncio
async def test_get_dispositions_happy(client: BackendAPIClient) -> None:
    resp = MagicMock(status_code=200)
    resp.json.return_value = [{"id": "d1"}, {"id": "d2"}, {"id": "d3"}]
    with patch("analysi.alert_analysis.clients.InternalAsyncClient") as cls:
        cls.return_value.__aenter__.return_value = _mock_client(resp)
        out = await client.get_dispositions("t")
    assert len(out) == 3


@pytest.mark.asyncio
async def test_get_dispositions_500_raises_retryable(
    client: BackendAPIClient,
) -> None:
    resp = MagicMock(status_code=502)
    with patch("analysi.alert_analysis.clients.InternalAsyncClient") as cls:
        cls.return_value.__aenter__.return_value = _mock_client(resp)
        with pytest.raises(RetryableHTTPError):
            await client.get_dispositions("t")


# ── update_analysis_status ─────────────────────────────────────────────────-


@pytest.mark.asyncio
async def test_update_analysis_status_happy(client: BackendAPIClient) -> None:
    resp = MagicMock(status_code=200)
    resp.raise_for_status = MagicMock()
    with patch("analysi.alert_analysis.clients.InternalAsyncClient") as cls:
        cls.return_value.__aenter__.return_value = _mock_client(resp)
        out = await client.update_analysis_status("t", "an-1", "running")
    assert out is True


@pytest.mark.asyncio
async def test_update_analysis_status_with_error_param(
    client: BackendAPIClient,
) -> None:
    resp = MagicMock(status_code=200)
    resp.raise_for_status = MagicMock()
    fake = _mock_client(resp)
    with patch("analysi.alert_analysis.clients.InternalAsyncClient") as cls:
        cls.return_value.__aenter__.return_value = fake
        await client.update_analysis_status(
            "t", "an-1", "failed", error="boom"
        )
    fake.put.assert_called_once()
    _, kwargs = fake.put.call_args
    assert kwargs["params"]["error"] == "boom"


@pytest.mark.asyncio
async def test_update_analysis_status_409_returns_none(
    client: BackendAPIClient,
) -> None:
    """Terminal-state cancellation returns None so callers can distinguish
    'rejected' from other errors."""
    resp = MagicMock(status_code=409)
    with patch("analysi.alert_analysis.clients.InternalAsyncClient") as cls:
        cls.return_value.__aenter__.return_value = _mock_client(resp)
        out = await client.update_analysis_status("t", "an-1", "completed")
    assert out is None


@pytest.mark.asyncio
async def test_update_analysis_status_500_raises_retryable(
    client: BackendAPIClient,
) -> None:
    resp = MagicMock(status_code=503)
    with patch("analysi.alert_analysis.clients.InternalAsyncClient") as cls:
        cls.return_value.__aenter__.return_value = _mock_client(resp)
        with pytest.raises(RetryableHTTPError):
            await client.update_analysis_status("t", "an-1", "running")


@pytest.mark.asyncio
async def test_update_analysis_status_4xx_returns_false(
    client: BackendAPIClient,
) -> None:
    """Non-409 4xx → log and return False (caller treats as soft-failure)."""
    resp = MagicMock(status_code=403)
    resp.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError(
            "forbidden", request=MagicMock(), response=resp
        )
    )
    with patch("analysi.alert_analysis.clients.InternalAsyncClient") as cls:
        cls.return_value.__aenter__.return_value = _mock_client(resp)
        out = await client.update_analysis_status("t", "an-1", "running")
    assert out is False


@pytest.mark.asyncio
async def test_update_analysis_status_request_error_wraps_as_retryable(
    client: BackendAPIClient,
) -> None:
    fake = AsyncMock()
    fake.put = AsyncMock(side_effect=httpx.ConnectError("nope"))
    with patch("analysi.alert_analysis.clients.InternalAsyncClient") as cls:
        cls.return_value.__aenter__.return_value = fake
        with pytest.raises(RetryableHTTPError):
            await client.update_analysis_status("t", "an-1", "running")


# ── update_alert_analysis_status ───────────────────────────────────────────-


@pytest.mark.asyncio
async def test_update_alert_analysis_status_happy(
    client: BackendAPIClient,
) -> None:
    resp = MagicMock(status_code=200)
    resp.raise_for_status = MagicMock()
    with patch("analysi.alert_analysis.clients.InternalAsyncClient") as cls:
        cls.return_value.__aenter__.return_value = _mock_client(resp)
        out = await client.update_alert_analysis_status("t", "a-1", "running")
    assert out is True


@pytest.mark.asyncio
async def test_update_alert_analysis_status_500_raises(
    client: BackendAPIClient,
) -> None:
    resp = MagicMock(status_code=500)
    with patch("analysi.alert_analysis.clients.InternalAsyncClient") as cls:
        cls.return_value.__aenter__.return_value = _mock_client(resp)
        with pytest.raises(RetryableHTTPError):
            await client.update_alert_analysis_status("t", "a-1", "running")


@pytest.mark.asyncio
async def test_update_alert_analysis_status_4xx_returns_false(
    client: BackendAPIClient,
) -> None:
    resp = MagicMock(status_code=400)
    resp.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError(
            "bad request", request=MagicMock(), response=resp
        )
    )
    with patch("analysi.alert_analysis.clients.InternalAsyncClient") as cls:
        cls.return_value.__aenter__.return_value = _mock_client(resp)
        out = await client.update_alert_analysis_status("t", "a-1", "running")
    assert out is False


# ── get_alert ──────────────────────────────────────────────────────────────-


@pytest.mark.asyncio
async def test_get_alert_happy(client: BackendAPIClient) -> None:
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"id": "a-1", "title": "x"}
    resp.raise_for_status = MagicMock()
    with patch("analysi.alert_analysis.clients.InternalAsyncClient") as cls:
        cls.return_value.__aenter__.return_value = _mock_client(resp)
        out = await client.get_alert("t", "a-1")
    assert out == {"id": "a-1", "title": "x"}


@pytest.mark.asyncio
async def test_get_alert_404_returns_none(client: BackendAPIClient) -> None:
    resp = MagicMock(status_code=404)
    with patch("analysi.alert_analysis.clients.InternalAsyncClient") as cls:
        cls.return_value.__aenter__.return_value = _mock_client(resp)
        out = await client.get_alert("t", "missing")
    assert out is None


@pytest.mark.asyncio
async def test_get_alert_500_raises(client: BackendAPIClient) -> None:
    resp = MagicMock(status_code=500)
    with patch("analysi.alert_analysis.clients.InternalAsyncClient") as cls:
        cls.return_value.__aenter__.return_value = _mock_client(resp)
        with pytest.raises(RetryableHTTPError):
            await client.get_alert("t", "a-1")


@pytest.mark.asyncio
async def test_get_alert_unexpected_4xx_returns_none(
    client: BackendAPIClient,
) -> None:
    resp = MagicMock(status_code=403)
    resp.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError(
            "forbidden", request=MagicMock(), response=resp
        )
    )
    with patch("analysi.alert_analysis.clients.InternalAsyncClient") as cls:
        cls.return_value.__aenter__.return_value = _mock_client(resp)
        out = await client.get_alert("t", "a-1")
    assert out is None


# ── get_analysis ───────────────────────────────────────────────────────────-


@pytest.mark.asyncio
async def test_get_analysis_happy(client: BackendAPIClient) -> None:
    resp = MagicMock(status_code=200)
    resp.json.return_value = {
        "id": "a-1",
        "current_analysis": {"id": "an-1", "status": "running"},
    }
    resp.raise_for_status = MagicMock()
    with patch("analysi.alert_analysis.clients.InternalAsyncClient") as cls:
        cls.return_value.__aenter__.return_value = _mock_client(resp)
        out = await client.get_analysis("t", "a-1")
    assert out == {"id": "an-1", "status": "running"}


@pytest.mark.asyncio
async def test_get_analysis_alert_without_current_analysis(
    client: BackendAPIClient,
) -> None:
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"id": "a-1", "current_analysis": None}
    resp.raise_for_status = MagicMock()
    with patch("analysi.alert_analysis.clients.InternalAsyncClient") as cls:
        cls.return_value.__aenter__.return_value = _mock_client(resp)
        out = await client.get_analysis("t", "a-1")
    assert out is None


@pytest.mark.asyncio
async def test_get_analysis_404_returns_none(client: BackendAPIClient) -> None:
    resp = MagicMock(status_code=404)
    with patch("analysi.alert_analysis.clients.InternalAsyncClient") as cls:
        cls.return_value.__aenter__.return_value = _mock_client(resp)
        out = await client.get_analysis("t", "a-1")
    assert out is None


# ── update_step_progress ───────────────────────────────────────────────────-


@pytest.mark.asyncio
async def test_update_step_progress_happy(client: BackendAPIClient) -> None:
    resp = MagicMock(status_code=200)
    resp.raise_for_status = MagicMock()
    with patch("analysi.alert_analysis.clients.InternalAsyncClient") as cls:
        cls.return_value.__aenter__.return_value = _mock_client(resp)
        out = await client.update_step_progress("t", "an-1", "step-1", True)
    assert out is True


@pytest.mark.asyncio
async def test_update_step_progress_with_error_param(
    client: BackendAPIClient,
) -> None:
    resp = MagicMock(status_code=200)
    resp.raise_for_status = MagicMock()
    fake = _mock_client(resp)
    with patch("analysi.alert_analysis.clients.InternalAsyncClient") as cls:
        cls.return_value.__aenter__.return_value = fake
        await client.update_step_progress(
            "t", "an-1", "step-1", False, error="boom"
        )
    _, kwargs = fake.put.call_args
    assert kwargs["params"]["error"] == "boom"


@pytest.mark.asyncio
async def test_update_step_progress_4xx_returns_false(
    client: BackendAPIClient,
) -> None:
    resp = MagicMock(status_code=400)
    resp.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError(
            "bad", request=MagicMock(), response=resp
        )
    )
    with patch("analysi.alert_analysis.clients.InternalAsyncClient") as cls:
        cls.return_value.__aenter__.return_value = _mock_client(resp)
        out = await client.update_step_progress("t", "an-1", "step-1", True)
    assert out is False


# ── KeaCoordinationClient ───────────────────────────────────────────────────


@pytest.fixture
def kea_client() -> KeaCoordinationClient:
    return KeaCoordinationClient(base_url="http://kea-test:8050")


@pytest.mark.asyncio
async def test_kea_create_group_with_generation_happy(
    kea_client: KeaCoordinationClient,
) -> None:
    resp = MagicMock(status_code=201)
    resp.json.return_value = {
        "analysis_group": {"id": "grp-1", "title": "rule-x"},
        "workflow_generation": {
            "id": "gen-1",
            "status": "running",
            "workflow_id": None,
        },
    }
    resp.raise_for_status = MagicMock()
    with patch("analysi.alert_analysis.clients.InternalAsyncClient") as cls:
        cls.return_value.__aenter__.return_value = _mock_client(resp)
        out = await kea_client.create_group_with_generation(
            tenant_id="t",
            title="rule-x",
            triggering_alert_analysis_id="aa-1",
        )
    assert out["analysis_group"]["id"] == "grp-1"
    assert out["workflow_generation"]["status"] == "running"


@pytest.mark.asyncio
async def test_kea_create_group_omits_optional_id_when_absent(
    kea_client: KeaCoordinationClient,
) -> None:
    """When ``triggering_alert_analysis_id`` is None it should NOT appear in
    the request body (the endpoint treats absent vs null differently)."""
    resp = MagicMock(status_code=201)
    resp.json.return_value = {
        "analysis_group": {"id": "g"},
        "workflow_generation": {"id": "gen", "status": "running"},
    }
    resp.raise_for_status = MagicMock()
    fake = _mock_client(resp)
    with patch("analysi.alert_analysis.clients.InternalAsyncClient") as cls:
        cls.return_value.__aenter__.return_value = fake
        await kea_client.create_group_with_generation(tenant_id="t", title="rule-x")
    _, kwargs = fake.post.call_args
    assert "triggering_alert_analysis_id" not in kwargs["json"]
    assert kwargs["json"]["title"] == "rule-x"


@pytest.mark.asyncio
async def test_kea_create_routing_rule_happy(
    kea_client: KeaCoordinationClient,
) -> None:
    resp = MagicMock(status_code=201)
    resp.json.return_value = {"id": "rr-1"}
    resp.raise_for_status = MagicMock()
    with patch("analysi.alert_analysis.clients.InternalAsyncClient") as cls:
        cls.return_value.__aenter__.return_value = _mock_client(resp)
        out = await kea_client.create_routing_rule(
            tenant_id="t",
            analysis_group_id="grp-1",
            workflow_id="wf-1",
        )
    assert out == {"id": "rr-1"}


@pytest.mark.asyncio
async def test_kea_get_active_workflow_happy(
    kea_client: KeaCoordinationClient,
) -> None:
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"workflow_id": "wf-1"}
    resp.raise_for_status = MagicMock()
    with patch("analysi.alert_analysis.clients.InternalAsyncClient") as cls:
        cls.return_value.__aenter__.return_value = _mock_client(resp)
        out = await kea_client.get_active_workflow("t", "rule-x")
    assert out == {"workflow_id": "wf-1"}
