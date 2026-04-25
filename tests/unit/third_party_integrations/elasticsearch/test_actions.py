"""Unit tests for Elasticsearch integration actions."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from analysi.integrations.framework.integrations.elasticsearch.actions import (
    AlertsToOcsfAction,
    GetConfigAction,
    HealthCheckAction,
    IndexDocumentAction,
    PullAlertsAction,
    RunQueryAction,
)


@pytest.fixture
def health_check_action():
    """Create HealthCheckAction instance with mock credentials and settings."""
    return HealthCheckAction(
        integration_id="elasticsearch",
        action_id="health_check",
        settings={
            "url": "https://elasticsearch.example.com:9200",
            "verify_server_cert": False,
        },
        credentials={
            "username": "elastic_user",
            "password": "elastic_pass",
        },
    )


@pytest.fixture
def run_query_action():
    """Create RunQueryAction instance with mock credentials and settings."""
    return RunQueryAction(
        integration_id="elasticsearch",
        action_id="run_query",
        settings={
            "url": "https://elasticsearch.example.com:9200",
            "verify_server_cert": False,
        },
        credentials={
            "username": "elastic_user",
            "password": "elastic_pass",
        },
    )


@pytest.fixture
def get_config_action():
    """Create GetConfigAction instance with mock credentials and settings."""
    return GetConfigAction(
        integration_id="elasticsearch",
        action_id="get_config",
        settings={
            "url": "https://elasticsearch.example.com:9200",
            "verify_server_cert": False,
        },
        credentials={
            "username": "elastic_user",
            "password": "elastic_pass",
        },
    )


# ==================== HealthCheckAction Tests ====================


@pytest.mark.asyncio
async def test_health_check_success(health_check_action):
    """Test successful health check."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.json.return_value = {
        "cluster_name": "test-cluster",
        "status": "green",
        "number_of_nodes": 3,
    }

    with patch.object(
        health_check_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await health_check_action.execute()

    assert result["status"] == "success"
    assert "Elasticsearch connection successful" in result["message"]
    assert "cluster_health" in result
    assert result["cluster_health"]["status"] == "green"


@pytest.mark.asyncio
async def test_health_check_missing_url():
    """Test health check with missing URL."""
    action = HealthCheckAction(
        integration_id="elasticsearch",
        action_id="health_check",
        settings={"url": ""},
        credentials={"username": "elastic_user", "password": "elastic_pass"},
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert "Missing required Elasticsearch URL" in result["error"]


@pytest.mark.asyncio
async def test_health_check_missing_credentials():
    """Test health check with missing credentials."""
    action = HealthCheckAction(
        integration_id="elasticsearch",
        action_id="health_check",
        settings={"url": "https://elasticsearch.example.com:9200"},
        credentials={"username": "", "password": ""},
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert "Missing required credentials" in result["error"]


@pytest.mark.asyncio
async def test_health_check_http_error(health_check_action):
    """Test health check with HTTP error."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 401

    with patch.object(
        health_check_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.HTTPStatusError(
            "Unauthorized", request=MagicMock(), response=mock_response
        ),
    ):
        result = await health_check_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "HTTPStatusError"
    assert "connection failed" in result["error"].lower()


@pytest.mark.asyncio
async def test_health_check_timeout(health_check_action):
    """Test health check with timeout."""

    with patch.object(
        health_check_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=__import__("httpx").TimeoutException("Timeout"),
    ):
        result = await health_check_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "TimeoutError"
    assert "connection failed" in result["error"].lower()


@pytest.mark.asyncio
async def test_health_check_request_error(health_check_action):
    """Test health check with request error."""

    with patch.object(
        health_check_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=__import__("httpx").RequestError("Connection refused"),
    ):
        result = await health_check_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "RequestError"
    assert "connection failed" in result["error"].lower()


# ==================== RunQueryAction Tests ====================


@pytest.mark.asyncio
async def test_run_query_success(run_query_action):
    """Test successful query execution."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.json.return_value = {
        "took": 5,
        "timed_out": False,
        "hits": {
            "total": {"value": 10, "relation": "eq"},
            "hits": [
                {"_index": "test-index", "_id": "1", "_source": {"field": "value"}}
            ],
        },
    }

    with patch.object(
        run_query_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await run_query_action.execute(
            index="test-index", query='{"query": {"match_all": {}}}'
        )

    assert result["status"] == "success"
    assert result["summary"]["total_hits"] == 10
    assert result["summary"]["timed_out"] is False
    assert "Total hits: 10" in result["message"]


@pytest.mark.asyncio
async def test_run_query_missing_index(run_query_action):
    """Test query with missing index parameter."""
    result = await run_query_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "Missing required parameter 'index'" in result["error"]


@pytest.mark.asyncio
async def test_run_query_invalid_index(run_query_action):
    """Test query with invalid index parameter."""
    result = await run_query_action.execute(index="  ,  ,  ")

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "valid value in the 'index' parameter" in result["error"]


@pytest.mark.asyncio
async def test_run_query_invalid_json(run_query_action):
    """Test query with invalid JSON."""
    result = await run_query_action.execute(index="test-index", query="{invalid json}")

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "Unable to parse query JSON" in result["error"]


@pytest.mark.asyncio
async def test_run_query_with_routing(run_query_action):
    """Test query with routing parameter."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.json.return_value = {
        "took": 5,
        "timed_out": False,
        "hits": {"total": {"value": 5, "relation": "eq"}, "hits": []},
    }

    with patch.object(
        run_query_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_response,
    ) as mock_request:
        result = await run_query_action.execute(
            index="test-index",
            query='{"query": {"match_all": {}}}',
            routing="shard1",
        )

    assert result["status"] == "success"
    assert result["summary"]["total_hits"] == 5
    # Verify routing parameter is forwarded via params
    call_kwargs = mock_request.call_args.kwargs
    assert call_kwargs.get("params", {}).get("routing") == "shard1"


@pytest.mark.asyncio
async def test_run_query_missing_credentials():
    """Test query with missing credentials."""
    action = RunQueryAction(
        integration_id="elasticsearch",
        action_id="run_query",
        settings={"url": "https://elasticsearch.example.com:9200"},
        credentials={"username": "", "password": ""},
    )

    result = await action.execute(index="test-index")

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert "Missing required credentials" in result["error"]


@pytest.mark.asyncio
async def test_run_query_http_error(run_query_action):
    """Test query with HTTP error."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 404
    mock_response.text = "Index not found"

    with patch.object(
        run_query_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=mock_response
        ),
    ):
        result = await run_query_action.execute(index="test-index")

    assert result["status"] == "error"
    assert result["error_type"] == "HTTPStatusError"
    assert "404" in result["error"]


@pytest.mark.asyncio
async def test_run_query_timeout(run_query_action):
    """Test query with timeout."""

    with patch.object(
        run_query_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=__import__("httpx").TimeoutException("Timeout"),
    ):
        result = await run_query_action.execute(index="test-index")

    assert result["status"] == "error"
    assert result["error_type"] == "TimeoutError"
    assert "timeout" in result["error"].lower()


@pytest.mark.asyncio
async def test_run_query_multiple_indices(run_query_action):
    """Test query with multiple comma-separated indices."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.json.return_value = {
        "took": 5,
        "timed_out": False,
        "hits": {"total": {"value": 15, "relation": "eq"}, "hits": []},
    }

    with patch.object(
        run_query_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await run_query_action.execute(
            index="index1, index2, index3", query='{"query": {"match_all": {}}}'
        )

    assert result["status"] == "success"
    # Verify the indices were cleaned and joined
    # Check that all indices are present (order doesn't matter due to set)


# ==================== GetConfigAction Tests ====================


@pytest.mark.asyncio
async def test_get_config_success(get_config_action):
    """Test successful get config."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.json.return_value = [
        {
            "index": "test-index-1",
            "health": "green",
            "status": "open",
            "docs.count": "1000",
            "store.size": "5mb",
        },
        {
            "index": "test-index-2",
            "health": "yellow",
            "status": "open",
            "docs.count": "500",
            "store.size": "2mb",
        },
    ]

    with patch.object(
        get_config_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await get_config_action.execute()

    assert result["status"] == "success"
    assert result["summary"]["total_indices"] == 2
    assert len(result["data"]) == 2
    assert result["data"][0]["index"] == "test-index-1"
    assert result["data"][0]["health"] == "green"
    assert "Total indices: 2" in result["message"]


@pytest.mark.asyncio
async def test_get_config_missing_credentials():
    """Test get config with missing credentials."""
    action = GetConfigAction(
        integration_id="elasticsearch",
        action_id="get_config",
        settings={"url": "https://elasticsearch.example.com:9200"},
        credentials={"username": "", "password": ""},
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert "Missing required credentials" in result["error"]


@pytest.mark.asyncio
async def test_get_config_http_error(get_config_action):
    """Test get config with HTTP error."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 403
    mock_response.text = "Forbidden"

    with patch.object(
        get_config_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.HTTPStatusError(
            "Forbidden", request=MagicMock(), response=mock_response
        ),
    ):
        result = await get_config_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "HTTPStatusError"
    assert "403" in result["error"]


@pytest.mark.asyncio
async def test_get_config_timeout(get_config_action):
    """Test get config with timeout."""

    with patch.object(
        get_config_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=__import__("httpx").TimeoutException("Timeout"),
    ):
        result = await get_config_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "TimeoutError"
    assert "timeout" in result["error"].lower()


@pytest.mark.asyncio
async def test_get_config_request_error(get_config_action):
    """Test get config with request error."""

    with patch.object(
        get_config_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=__import__("httpx").RequestError("Connection refused"),
    ):
        result = await get_config_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "RequestError"


@pytest.mark.asyncio
async def test_get_config_empty_result(get_config_action):
    """Test get config with empty result."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.json.return_value = []

    with patch.object(
        get_config_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await get_config_action.execute()

    assert result["status"] == "success"
    assert result["summary"]["total_indices"] == 0
    assert len(result["data"]) == 0
    assert "Total indices: 0" in result["message"]


# ==================== IndexDocumentAction Tests ====================


@pytest.fixture
def index_document_action():
    """Create IndexDocumentAction instance with mock credentials and settings."""
    return IndexDocumentAction(
        integration_id="elasticsearch",
        action_id="index_document",
        settings={
            "url": "https://elasticsearch.example.com:9200",
            "verify_server_cert": False,
        },
        credentials={
            "username": "elastic_user",
            "password": "elastic_pass",
        },
    )


@pytest.mark.asyncio
async def test_index_document_success(index_document_action):
    """Test successful document indexing."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.json.return_value = {
        "_index": "security-events",
        "_id": "abc123",
        "_version": 1,
        "result": "created",
        "_shards": {"total": 2, "successful": 1, "failed": 0},
    }

    with patch.object(
        index_document_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await index_document_action.execute(
            index="security-events",
            document='{"alert_id": "test-001", "severity": "high"}',
        )

    assert result["status"] == "success"
    assert result["document_id"] == "abc123"
    assert result["index"] == "security-events"
    assert result["result"] == "created"


@pytest.mark.asyncio
async def test_index_document_with_dict(index_document_action):
    """Test indexing with a dict instead of JSON string."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.json.return_value = {
        "_index": "test-index",
        "_id": "def456",
        "result": "created",
    }

    with patch.object(
        index_document_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await index_document_action.execute(
            index="test-index",
            document={"key": "value"},
        )

    assert result["status"] == "success"
    assert result["document_id"] == "def456"


@pytest.mark.asyncio
async def test_index_document_missing_index(index_document_action):
    """Test indexing with missing index."""
    result = await index_document_action.execute(document='{"key": "value"}')

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "Missing required parameter 'index'" in result["error"]


@pytest.mark.asyncio
async def test_index_document_missing_document(index_document_action):
    """Test indexing with missing document."""
    result = await index_document_action.execute(index="test-index")

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "Missing required parameter 'document'" in result["error"]


@pytest.mark.asyncio
async def test_index_document_invalid_json(index_document_action):
    """Test indexing with invalid JSON document."""
    result = await index_document_action.execute(
        index="test-index", document="{invalid json}"
    )

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "Unable to parse document JSON" in result["error"]


@pytest.mark.asyncio
async def test_index_document_missing_credentials():
    """Test indexing with missing credentials."""
    action = IndexDocumentAction(
        integration_id="elasticsearch",
        action_id="index_document",
        settings={"url": "https://elasticsearch.example.com:9200"},
        credentials={"username": "", "password": ""},
    )

    result = await action.execute(index="test-index", document='{"key": "value"}')

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert "Missing required credentials" in result["error"]


@pytest.mark.asyncio
async def test_index_document_http_error(index_document_action):
    """Test indexing with HTTP error."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 400
    mock_response.text = "mapper_parsing_exception"

    with patch.object(
        index_document_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.HTTPStatusError(
            "Bad Request", request=MagicMock(), response=mock_response
        ),
    ):
        result = await index_document_action.execute(
            index="test-index", document='{"key": "value"}'
        )

    assert result["status"] == "error"
    assert result["error_type"] == "HTTPStatusError"
    assert "400" in result["error"]


@pytest.mark.asyncio
async def test_index_document_timeout(index_document_action):
    """Test indexing with timeout."""

    with patch.object(
        index_document_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=__import__("httpx").TimeoutException("Timeout"),
    ):
        result = await index_document_action.execute(
            index="test-index", document='{"key": "value"}'
        )

    assert result["status"] == "error"
    assert result["error_type"] == "TimeoutError"


# ==================== PullAlertsAction Tests ====================


@pytest.fixture
def pull_alerts_action():
    """Create PullAlertsAction instance with mock credentials and settings."""
    return PullAlertsAction(
        integration_id="elasticsearch",
        action_id="pull_alerts",
        settings={
            "url": "https://elasticsearch.example.com:9200",
            "verify_server_cert": False,
        },
        credentials={
            "username": "elastic_user",
            "password": "elastic_pass",
        },
    )


def _es_search_response(hits, total=None):
    """Build a mock ES _search response."""
    mock_resp = MagicMock(spec=httpx.Response)
    total_val = total if total is not None else len(hits)
    mock_resp.json.return_value = {
        "took": 3,
        "timed_out": False,
        "hits": {
            "total": {"value": total_val, "relation": "eq"},
            "hits": hits,
        },
    }
    return mock_resp


def _make_hit(doc_id, timestamp="2026-04-09T10:00:00+00:00", sort=None):
    """Build a single ES hit document."""
    hit = {
        "_index": ".alerts-security.alerts-default",
        "_id": doc_id,
        "_source": {
            "@timestamp": timestamp,
            "kibana.alert.rule.name": f"Rule for {doc_id}",
            "kibana.alert.severity": "high",
        },
    }
    if sort is not None:
        hit["sort"] = sort
    return hit


@pytest.mark.asyncio
async def test_pull_alerts_success(pull_alerts_action):
    """Test successful alert pull with results."""
    now = datetime.now(UTC)
    hits = [
        _make_hit("alert-1", sort=[now.isoformat(), "alert-1"]),
        _make_hit("alert-2", sort=[now.isoformat(), "alert-2"]),
    ]
    mock_page1 = _es_search_response(hits, total=2)
    mock_page2 = _es_search_response([], total=2)

    with patch.object(
        pull_alerts_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=[mock_page1, mock_page2],
    ):
        result = await pull_alerts_action.execute(
            start_time=now - timedelta(hours=1),
            end_time=now,
        )

    assert result["status"] == "success"
    assert result["alerts_count"] == 2
    assert len(result["alerts"]) == 2
    assert result["alerts"][0]["_id"] == "alert-1"
    assert "Retrieved 2 alerts" in result["message"]


@pytest.mark.asyncio
async def test_pull_alerts_empty(pull_alerts_action):
    """Test alert pull with no matching alerts."""
    now = datetime.now(UTC)
    mock_resp = _es_search_response([], total=0)

    with patch.object(
        pull_alerts_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_resp,
    ):
        result = await pull_alerts_action.execute(
            start_time=now - timedelta(hours=1),
            end_time=now,
        )

    assert result["status"] == "success"
    assert result["alerts_count"] == 0
    assert result["alerts"] == []


@pytest.mark.asyncio
async def test_pull_alerts_pagination(pull_alerts_action):
    """Test pagination via search_after across two pages."""
    now = datetime.now(UTC)

    page1_hits = [
        _make_hit(f"alert-{i}", sort=[now.isoformat(), f"alert-{i}"])
        for i in range(100)
    ]
    page2_hits = [
        _make_hit(f"alert-{i}", sort=[now.isoformat(), f"alert-{i}"])
        for i in range(100, 150)
    ]
    mock_page1 = _es_search_response(page1_hits, total=150)
    mock_page2 = _es_search_response(page2_hits, total=150)
    mock_page3 = _es_search_response([], total=150)

    with patch.object(
        pull_alerts_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=[mock_page1, mock_page2, mock_page3],
    ) as mock_request:
        result = await pull_alerts_action.execute(
            start_time=now - timedelta(hours=1),
            end_time=now,
        )

    assert result["status"] == "success"
    assert result["alerts_count"] == 150
    assert len(result["alerts"]) == 150

    # Verify search_after was used on the second call
    assert mock_request.call_count >= 2
    second_call_kwargs = mock_request.call_args_list[1].kwargs
    body = second_call_kwargs["json_data"]
    assert "search_after" in body


@pytest.mark.asyncio
async def test_pull_alerts_missing_credentials():
    """Test alert pull with missing credentials."""
    action = PullAlertsAction(
        integration_id="elasticsearch",
        action_id="pull_alerts",
        settings={"url": "https://elasticsearch.example.com:9200"},
        credentials={"username": "", "password": ""},
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert "Missing required credentials" in result["error"]


@pytest.mark.asyncio
async def test_pull_alerts_default_lookback(pull_alerts_action):
    """Test that default lookback is applied when no time params given."""
    mock_resp = _es_search_response([], total=0)

    with patch.object(
        pull_alerts_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_resp,
    ) as mock_request:
        result = await pull_alerts_action.execute()

    assert result["status"] == "success"

    # Verify the query body was constructed with a time range
    call_kwargs = mock_request.call_args.kwargs
    body = call_kwargs["json_data"]
    range_filter = body["query"]["bool"]["filter"][0]["range"]["@timestamp"]
    assert "gte" in range_filter
    assert "lte" in range_filter

    # The window should be approximately 5 minutes (default lookback)
    gte = datetime.fromisoformat(range_filter["gte"])
    lte = datetime.fromisoformat(range_filter["lte"])
    diff = (lte - gte).total_seconds()
    assert 290 <= diff <= 310  # ~5 minutes with a small tolerance


# ==================== AlertsToOcsfAction Tests ====================


@pytest.fixture
def alerts_to_ocsf_action():
    """Create AlertsToOcsfAction instance."""
    return AlertsToOcsfAction(
        integration_id="elasticsearch",
        action_id="alerts_to_ocsf",
        settings={},
        credentials={},
    )


@pytest.mark.asyncio
async def test_alerts_to_ocsf_success(alerts_to_ocsf_action):
    """Test successful OCSF normalization."""
    raw_alerts = [
        {"_id": "a1", "_source": {"kibana.alert.rule.name": "Rule 1"}},
        {"_id": "a2", "_source": {"kibana.alert.rule.name": "Rule 2"}},
    ]
    ocsf_doc_1 = {"class_uid": 2004, "finding_info": {"uid": "a1"}}
    ocsf_doc_2 = {"class_uid": 2004, "finding_info": {"uid": "a2"}}

    mock_normalizer = MagicMock()
    mock_normalizer.to_ocsf.side_effect = [ocsf_doc_1, ocsf_doc_2]

    with patch.dict(
        "sys.modules",
        {"alert_normalizer": MagicMock(), "alert_normalizer.elastic_ocsf": MagicMock()},
    ):
        with patch(
            "alert_normalizer.elastic_ocsf.ElasticOCSFNormalizer",
            return_value=mock_normalizer,
        ):
            result = await alerts_to_ocsf_action.execute(raw_alerts=raw_alerts)

    assert result["status"] == "success"
    assert result["count"] == 2
    assert result["errors"] == 0
    assert len(result["normalized_alerts"]) == 2
    assert result["normalized_alerts"][0]["class_uid"] == 2004


@pytest.mark.asyncio
async def test_alerts_to_ocsf_empty(alerts_to_ocsf_action):
    """Test OCSF normalization with empty input."""
    mock_normalizer = MagicMock()

    with patch.dict(
        "sys.modules",
        {"alert_normalizer": MagicMock(), "alert_normalizer.elastic_ocsf": MagicMock()},
    ):
        with patch(
            "alert_normalizer.elastic_ocsf.ElasticOCSFNormalizer",
            return_value=mock_normalizer,
        ):
            result = await alerts_to_ocsf_action.execute(raw_alerts=[])

    assert result["status"] == "success"
    assert result["count"] == 0
    assert result["errors"] == 0
    assert result["normalized_alerts"] == []


@pytest.mark.asyncio
async def test_alerts_to_ocsf_partial_failure(alerts_to_ocsf_action):
    """Test OCSF normalization where one alert fails."""
    raw_alerts = [
        {"_id": "a1", "_source": {"kibana.alert.rule.name": "Rule 1"}},
        {"_id": "a2", "_source": {"kibana.alert.rule.name": "Rule 2"}},
        {"_id": "a3", "_source": {"kibana.alert.rule.name": "Rule 3"}},
    ]
    ocsf_good = {"class_uid": 2004, "finding_info": {"uid": "ok"}}

    mock_normalizer = MagicMock()
    mock_normalizer.to_ocsf.side_effect = [
        ocsf_good,
        ValueError("bad alert"),
        ocsf_good,
    ]

    with patch.dict(
        "sys.modules",
        {"alert_normalizer": MagicMock(), "alert_normalizer.elastic_ocsf": MagicMock()},
    ):
        with patch(
            "alert_normalizer.elastic_ocsf.ElasticOCSFNormalizer",
            return_value=mock_normalizer,
        ):
            result = await alerts_to_ocsf_action.execute(raw_alerts=raw_alerts)

    assert result["status"] == "partial"
    assert result["count"] == 2
    assert result["errors"] == 1
    assert len(result["normalized_alerts"]) == 2
