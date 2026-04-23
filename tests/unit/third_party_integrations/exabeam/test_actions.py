"""Unit tests for Exabeam Advanced Analytics integration actions."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from analysi.integrations.framework.integrations.exabeam.actions import (
    AddToWatchlistAction,
    GetAssetAction,
    GetUserAction,
    GetWatchlistAction,
    HealthCheckAction,
    ListWatchlistsAction,
    RemoveFromWatchlistAction,
    SearchAssetsAction,
    SearchUsersAction,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_SETTINGS = {
    "base_url": "https://exabeam.example.com:8484/api",
    "verify_ssl": False,
}

VALID_CREDENTIALS = {
    "username": "admin",
    "password": "s3cret",
}


def _make_action(cls, *, settings=None, credentials=None):
    """Helper to build an action instance with optional overrides."""
    return cls(
        integration_id="exabeam",
        action_id=cls.__name__.replace("Action", "").lower(),
        settings=settings or {**VALID_SETTINGS},
        credentials=credentials or {**VALID_CREDENTIALS},
    )


@pytest.fixture
def health_check_action():
    return _make_action(HealthCheckAction)


@pytest.fixture
def get_user_action():
    return _make_action(GetUserAction)


@pytest.fixture
def search_users_action():
    return _make_action(SearchUsersAction)


@pytest.fixture
def get_watchlist_action():
    return _make_action(GetWatchlistAction)


@pytest.fixture
def list_watchlists_action():
    return _make_action(ListWatchlistsAction)


@pytest.fixture
def add_to_watchlist_action():
    return _make_action(AddToWatchlistAction)


@pytest.fixture
def remove_from_watchlist_action():
    return _make_action(RemoveFromWatchlistAction)


@pytest.fixture
def search_assets_action():
    return _make_action(SearchAssetsAction)


@pytest.fixture
def get_asset_action():
    return _make_action(GetAssetAction)


def _mock_json_response(body: dict, status_code: int = 200) -> MagicMock:
    """Create a mock httpx.Response with a JSON body."""
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = body
    resp.status_code = status_code
    resp.text = str(body)
    return resp


# ==================== HealthCheckAction Tests ====================


@pytest.mark.asyncio
async def test_health_check_success(health_check_action):
    """Test successful health check returns healthy status."""
    mock_response = _mock_json_response({"users": [{"id": "1"}, {"id": "2"}]})

    with patch.object(
        health_check_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await health_check_action.execute()

    assert result["status"] == "success"
    assert result["healthy"] is True
    assert result["data"]["watchlist_count"] == 2
    assert "Exabeam connection successful" in result["message"]
    assert "timestamp" in result
    assert result["integration_id"] == "exabeam"
    assert result["action_id"] == "healthcheck"


@pytest.mark.asyncio
async def test_health_check_missing_base_url():
    """Test health check with missing base URL."""
    action = _make_action(HealthCheckAction, settings={"base_url": ""})
    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert result["healthy"] is False
    assert "base_url" in result["error"]
    assert result["integration_id"] == "exabeam"


@pytest.mark.asyncio
async def test_health_check_missing_credentials():
    """Test health check with missing credentials."""
    action = _make_action(
        HealthCheckAction,
        credentials={"username": "", "password": ""},
    )
    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert result["healthy"] is False
    assert "credentials" in result["error"].lower()


@pytest.mark.asyncio
async def test_health_check_http_error(health_check_action):
    """Test health check handles HTTP 401."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 401
    mock_response.text = "Unauthorized"

    with patch.object(
        health_check_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.HTTPStatusError(
            "Unauthorized",
            request=MagicMock(),
            response=mock_response,
        ),
    ):
        result = await health_check_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "HTTPStatusError"
    assert result["healthy"] is False


@pytest.mark.asyncio
async def test_health_check_timeout(health_check_action):
    """Test health check handles timeout."""
    with patch.object(
        health_check_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.TimeoutException("Connection timed out"),
    ):
        result = await health_check_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "TimeoutError"
    assert result["healthy"] is False


@pytest.mark.asyncio
async def test_health_check_request_error(health_check_action):
    """Test health check handles connection refused."""
    with patch.object(
        health_check_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.RequestError("Connection refused"),
    ):
        result = await health_check_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "RequestError"
    assert result["healthy"] is False


# ==================== GetUserAction Tests ====================


@pytest.mark.asyncio
async def test_get_user_success(get_user_action):
    """Test successful user lookup with risk score data."""
    user_data = {
        "userInfo": {
            "username": "jdoe",
            "riskScore": 85,
            "averageRiskScore": 72,
            "labels": ["Executive"],
        },
        "accountNames": ["jdoe@corp.com"],
        "executive": True,
        "onWatchlist": False,
    }
    mock_response = _mock_json_response(user_data)

    with patch.object(
        get_user_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await get_user_action.execute(username="jdoe")

    assert result["status"] == "success"
    assert result["data"]["userInfo"]["riskScore"] == 85
    assert result["data"]["executive"] is True


@pytest.mark.asyncio
async def test_get_user_missing_username(get_user_action):
    """Test get user with missing username parameter."""
    result = await get_user_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "username" in result["error"]


@pytest.mark.asyncio
async def test_get_user_missing_credentials():
    """Test get user with missing credentials."""
    action = _make_action(
        GetUserAction,
        credentials={"username": "", "password": ""},
    )
    result = await action.execute(username="jdoe")

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"


@pytest.mark.asyncio
async def test_get_user_not_found(get_user_action):
    """Test get user returns not_found for 404."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 404
    mock_response.text = "Not Found"

    with patch.object(
        get_user_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.HTTPStatusError(
            "Not Found",
            request=MagicMock(),
            response=mock_response,
        ),
    ):
        result = await get_user_action.execute(username="nonexistent")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["data"]["username"] == "nonexistent"


@pytest.mark.asyncio
async def test_get_user_http_error(get_user_action):
    """Test get user with non-404 HTTP error."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"

    with patch.object(
        get_user_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.HTTPStatusError(
            "Server Error",
            request=MagicMock(),
            response=mock_response,
        ),
    ):
        result = await get_user_action.execute(username="jdoe")

    assert result["status"] == "error"
    assert result["error_type"] == "HTTPStatusError"
    assert result["integration_id"] == "exabeam"


@pytest.mark.asyncio
async def test_get_user_timeout(get_user_action):
    """Test get user handles timeout."""
    with patch.object(
        get_user_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.TimeoutException("Timeout"),
    ):
        result = await get_user_action.execute(username="jdoe")

    assert result["status"] == "error"
    assert result["error_type"] == "TimeoutError"


# ==================== SearchUsersAction Tests ====================


@pytest.mark.asyncio
async def test_search_users_success(search_users_action):
    """Test successful user search with results."""
    mock_response = _mock_json_response(
        {
            "users": [
                {"username": "jdoe", "riskScore": 85},
                {"username": "jsmith", "riskScore": 42},
            ],
        }
    )

    with patch.object(
        search_users_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await search_users_action.execute(keyword="j")

    assert result["status"] == "success"
    assert result["summary"]["matches"] == 2
    assert len(result["data"]["users"]) == 2
    assert "Found 2 user(s)" in result["message"]


@pytest.mark.asyncio
async def test_search_users_empty_results(search_users_action):
    """Test search users with no matches."""
    mock_response = _mock_json_response({"users": []})

    with patch.object(
        search_users_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await search_users_action.execute(keyword="zzzzzzz")

    assert result["status"] == "success"
    assert result["summary"]["matches"] == 0


@pytest.mark.asyncio
async def test_search_users_missing_keyword(search_users_action):
    """Test search users with missing keyword."""
    result = await search_users_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "keyword" in result["error"]


@pytest.mark.asyncio
async def test_search_users_with_limit(search_users_action):
    """Test search users forwards the limit parameter."""
    mock_response = _mock_json_response({"users": [{"username": "jdoe"}]})

    with patch.object(
        search_users_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_response,
    ) as mock_req:
        result = await search_users_action.execute(keyword="j", limit=10)

    assert result["status"] == "success"
    call_kwargs = mock_req.call_args.kwargs
    assert call_kwargs["params"]["limit"] == 10


@pytest.mark.asyncio
async def test_search_users_missing_credentials():
    """Test search users with missing credentials."""
    action = _make_action(
        SearchUsersAction,
        credentials={"username": "", "password": ""},
    )
    result = await action.execute(keyword="test")

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"


@pytest.mark.asyncio
async def test_search_users_http_error(search_users_action):
    """Test search users with HTTP error."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 503
    mock_response.text = "Service Unavailable"

    with patch.object(
        search_users_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.HTTPStatusError(
            "Unavailable",
            request=MagicMock(),
            response=mock_response,
        ),
    ):
        result = await search_users_action.execute(keyword="test")

    assert result["status"] == "error"
    assert result["error_type"] == "HTTPStatusError"


# ==================== GetWatchlistAction Tests ====================


@pytest.mark.asyncio
async def test_get_watchlist_success(get_watchlist_action):
    """Test successful watchlist retrieval."""
    mock_response = _mock_json_response(
        {
            "title": "Executive Watch",
            "category": "executive",
            "users": [
                {"user": {"username": "exec1", "riskScore": 90}},
                {"user": {"username": "exec2", "riskScore": 60}},
            ],
        }
    )

    with patch.object(
        get_watchlist_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await get_watchlist_action.execute(watchlist_id="wl-001")

    assert result["status"] == "success"
    assert result["summary"]["users"] == 2
    assert "wl-001" in result["message"]


@pytest.mark.asyncio
async def test_get_watchlist_missing_id(get_watchlist_action):
    """Test get watchlist with missing watchlist_id."""
    result = await get_watchlist_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "watchlist_id" in result["error"]


@pytest.mark.asyncio
async def test_get_watchlist_not_found(get_watchlist_action):
    """Test get watchlist returns not_found for 404."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 404
    mock_response.text = "Not Found"

    with patch.object(
        get_watchlist_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.HTTPStatusError(
            "Not Found",
            request=MagicMock(),
            response=mock_response,
        ),
    ):
        result = await get_watchlist_action.execute(watchlist_id="nonexistent")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["data"]["watchlist_id"] == "nonexistent"


@pytest.mark.asyncio
async def test_get_watchlist_timeout(get_watchlist_action):
    """Test get watchlist handles timeout."""
    with patch.object(
        get_watchlist_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.TimeoutException("Timeout"),
    ):
        result = await get_watchlist_action.execute(watchlist_id="wl-001")

    assert result["status"] == "error"
    assert result["error_type"] == "TimeoutError"


# ==================== ListWatchlistsAction Tests ====================


@pytest.mark.asyncio
async def test_list_watchlists_success(list_watchlists_action):
    """Test successful watchlist listing."""
    mock_response = _mock_json_response(
        {
            "users": [
                {"watchlistId": "wl-001", "title": "Executives"},
                {"watchlistId": "wl-002", "title": "Contractors"},
            ],
        }
    )

    with patch.object(
        list_watchlists_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await list_watchlists_action.execute()

    assert result["status"] == "success"
    assert "watchlists" in result["data"]
    assert result["summary"]["matches"] == 2


@pytest.mark.asyncio
async def test_list_watchlists_empty(list_watchlists_action):
    """Test listing when no watchlists exist."""
    mock_response = _mock_json_response({"users": []})

    with patch.object(
        list_watchlists_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await list_watchlists_action.execute()

    assert result["status"] == "success"
    assert result["summary"]["matches"] == 0


@pytest.mark.asyncio
async def test_list_watchlists_missing_credentials():
    """Test list watchlists with missing credentials."""
    action = _make_action(
        ListWatchlistsAction,
        credentials={"username": "", "password": ""},
    )
    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"


@pytest.mark.asyncio
async def test_list_watchlists_http_error(list_watchlists_action):
    """Test list watchlists with HTTP error."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 403
    mock_response.text = "Forbidden"

    with patch.object(
        list_watchlists_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.HTTPStatusError(
            "Forbidden",
            request=MagicMock(),
            response=mock_response,
        ),
    ):
        result = await list_watchlists_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "HTTPStatusError"


# ==================== AddToWatchlistAction Tests ====================


@pytest.mark.asyncio
async def test_add_to_watchlist_success(add_to_watchlist_action):
    """Test successfully adding a user to a watchlist."""
    mock_response = _mock_json_response(
        {"success": True, "username": "jdoe", "watchlistId": "wl-001"},
    )

    with patch.object(
        add_to_watchlist_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await add_to_watchlist_action.execute(
            username="jdoe",
            watchlist_id="wl-001",
        )

    assert result["status"] == "success"
    assert result["data"]["success"] is True
    assert "jdoe" in result["message"]


@pytest.mark.asyncio
async def test_add_to_watchlist_with_duration(add_to_watchlist_action):
    """Test adding a user with a duration parameter."""
    mock_response = _mock_json_response({"success": True})

    with patch.object(
        add_to_watchlist_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_response,
    ) as mock_req:
        result = await add_to_watchlist_action.execute(
            username="jdoe",
            watchlist_id="wl-001",
            duration=30,
        )

    assert result["status"] == "success"
    call_kwargs = mock_req.call_args.kwargs
    assert call_kwargs["data"]["duration"] == 30


@pytest.mark.asyncio
async def test_add_to_watchlist_missing_username(add_to_watchlist_action):
    """Test add to watchlist with missing username."""
    result = await add_to_watchlist_action.execute(watchlist_id="wl-001")

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "username" in result["error"]


@pytest.mark.asyncio
async def test_add_to_watchlist_missing_watchlist_id(add_to_watchlist_action):
    """Test add to watchlist with missing watchlist_id."""
    result = await add_to_watchlist_action.execute(username="jdoe")

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "watchlist_id" in result["error"]


@pytest.mark.asyncio
async def test_add_to_watchlist_missing_credentials():
    """Test add to watchlist with missing credentials."""
    action = _make_action(
        AddToWatchlistAction,
        credentials={"username": "", "password": ""},
    )
    result = await action.execute(username="jdoe", watchlist_id="wl-001")

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"


@pytest.mark.asyncio
async def test_add_to_watchlist_http_error(add_to_watchlist_action):
    """Test add to watchlist with HTTP error."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"

    with patch.object(
        add_to_watchlist_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.HTTPStatusError(
            "Server Error",
            request=MagicMock(),
            response=mock_response,
        ),
    ):
        result = await add_to_watchlist_action.execute(
            username="jdoe",
            watchlist_id="wl-001",
        )

    assert result["status"] == "error"
    assert result["error_type"] == "HTTPStatusError"


@pytest.mark.asyncio
async def test_add_to_watchlist_uses_put_method(add_to_watchlist_action):
    """Test that add to watchlist uses the PUT HTTP method ."""
    mock_response = _mock_json_response({"success": True})

    with patch.object(
        add_to_watchlist_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_response,
    ) as mock_req:
        await add_to_watchlist_action.execute(
            username="jdoe",
            watchlist_id="wl-001",
        )

    call_kwargs = mock_req.call_args.kwargs
    assert call_kwargs["method"] == "PUT"


# ==================== RemoveFromWatchlistAction Tests ====================


@pytest.mark.asyncio
async def test_remove_from_watchlist_success(remove_from_watchlist_action):
    """Test successfully removing a user from a watchlist."""
    mock_response = _mock_json_response(
        {"success": True, "username": "jdoe", "watchlistId": "wl-001"},
    )

    with patch.object(
        remove_from_watchlist_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await remove_from_watchlist_action.execute(
            username="jdoe",
            watchlist_id="wl-001",
        )

    assert result["status"] == "success"
    assert "jdoe" in result["message"]


@pytest.mark.asyncio
async def test_remove_from_watchlist_missing_username(remove_from_watchlist_action):
    """Test remove from watchlist with missing username."""
    result = await remove_from_watchlist_action.execute(watchlist_id="wl-001")

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "username" in result["error"]


@pytest.mark.asyncio
async def test_remove_from_watchlist_missing_watchlist_id(remove_from_watchlist_action):
    """Test remove from watchlist with missing watchlist_id."""
    result = await remove_from_watchlist_action.execute(username="jdoe")

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "watchlist_id" in result["error"]


@pytest.mark.asyncio
async def test_remove_from_watchlist_uses_put_method(remove_from_watchlist_action):
    """Test that remove from watchlist uses the PUT HTTP method."""
    mock_response = _mock_json_response({"success": True})

    with patch.object(
        remove_from_watchlist_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_response,
    ) as mock_req:
        await remove_from_watchlist_action.execute(
            username="jdoe",
            watchlist_id="wl-001",
        )

    call_kwargs = mock_req.call_args.kwargs
    assert call_kwargs["method"] == "PUT"


@pytest.mark.asyncio
async def test_remove_from_watchlist_missing_credentials():
    """Test remove from watchlist with missing credentials."""
    action = _make_action(
        RemoveFromWatchlistAction,
        credentials={"username": "", "password": ""},
    )
    result = await action.execute(username="jdoe", watchlist_id="wl-001")

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"


@pytest.mark.asyncio
async def test_remove_from_watchlist_timeout(remove_from_watchlist_action):
    """Test remove from watchlist handles timeout."""
    with patch.object(
        remove_from_watchlist_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.TimeoutException("Timeout"),
    ):
        result = await remove_from_watchlist_action.execute(
            username="jdoe",
            watchlist_id="wl-001",
        )

    assert result["status"] == "error"
    assert result["error_type"] == "TimeoutError"


# ==================== SearchAssetsAction Tests ====================


@pytest.mark.asyncio
async def test_search_assets_success(search_assets_action):
    """Test successful asset search."""
    mock_response = _mock_json_response(
        {
            "assets": [
                {"hostName": "srv-01", "ipAddress": "10.0.0.1", "riskState": "High"},
                {"hostName": "srv-02", "ipAddress": "10.0.0.2", "riskState": "Low"},
            ],
        }
    )

    with patch.object(
        search_assets_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await search_assets_action.execute(keyword="srv")

    assert result["status"] == "success"
    assert result["summary"]["matches"] == 2
    assert "Found 2 asset(s)" in result["message"]


@pytest.mark.asyncio
async def test_search_assets_missing_keyword(search_assets_action):
    """Test search assets with missing keyword."""
    result = await search_assets_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "keyword" in result["error"]


@pytest.mark.asyncio
async def test_search_assets_with_limit(search_assets_action):
    """Test search assets forwards limit parameter."""
    mock_response = _mock_json_response({"assets": []})

    with patch.object(
        search_assets_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_response,
    ) as mock_req:
        result = await search_assets_action.execute(keyword="host", limit=5)

    assert result["status"] == "success"
    call_kwargs = mock_req.call_args.kwargs
    assert call_kwargs["params"]["limit"] == 5


@pytest.mark.asyncio
async def test_search_assets_missing_credentials():
    """Test search assets with missing credentials."""
    action = _make_action(
        SearchAssetsAction,
        credentials={"username": "", "password": ""},
    )
    result = await action.execute(keyword="host")

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"


@pytest.mark.asyncio
async def test_search_assets_http_error(search_assets_action):
    """Test search assets with HTTP error."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 502
    mock_response.text = "Bad Gateway"

    with patch.object(
        search_assets_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.HTTPStatusError(
            "Bad Gateway",
            request=MagicMock(),
            response=mock_response,
        ),
    ):
        result = await search_assets_action.execute(keyword="host")

    assert result["status"] == "error"
    assert result["error_type"] == "HTTPStatusError"


# ==================== GetAssetAction Tests ====================


@pytest.mark.asyncio
async def test_get_asset_by_hostname(get_asset_action):
    """Test get asset using hostname."""
    asset_data = {
        "location": "us-east",
        "zone": "DMZ",
        "topUsers": {"confidenceFactor": 0.8},
    }
    mock_response = _mock_json_response(asset_data)

    with patch.object(
        get_asset_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_response,
    ) as mock_req:
        result = await get_asset_action.execute(hostname="srv-web-01")

    assert result["status"] == "success"
    assert result["data"]["location"] == "us-east"
    # Verify endpoint uses the hostname
    called_url = mock_req.call_args.args[0]
    assert "srv-web-01" in called_url


@pytest.mark.asyncio
async def test_get_asset_by_ip(get_asset_action):
    """Test get asset using IP address."""
    mock_response = _mock_json_response({"location": "eu-west"})

    with patch.object(
        get_asset_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_response,
    ) as mock_req:
        result = await get_asset_action.execute(ip="10.0.0.5")

    assert result["status"] == "success"
    called_url = mock_req.call_args.args[0]
    assert "10.0.0.5" in called_url


@pytest.mark.asyncio
async def test_get_asset_hostname_takes_priority(get_asset_action):
    """Test hostname is preferred over IP when both are provided."""
    mock_response = _mock_json_response({"location": "us-east"})

    with patch.object(
        get_asset_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_response,
    ) as mock_req:
        result = await get_asset_action.execute(hostname="srv-01", ip="10.0.0.1")

    assert result["status"] == "success"
    called_url = mock_req.call_args.args[0]
    assert "srv-01" in called_url


@pytest.mark.asyncio
async def test_get_asset_missing_both_params(get_asset_action):
    """Test get asset with neither hostname nor ip."""
    result = await get_asset_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "hostname" in result["error"].lower() or "ip" in result["error"].lower()


@pytest.mark.asyncio
async def test_get_asset_not_found(get_asset_action):
    """Test get asset returns not_found for 404."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 404
    mock_response.text = "Not Found"

    with patch.object(
        get_asset_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.HTTPStatusError(
            "Not Found",
            request=MagicMock(),
            response=mock_response,
        ),
    ):
        result = await get_asset_action.execute(hostname="nonexistent")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["data"]["asset_id"] == "nonexistent"


@pytest.mark.asyncio
async def test_get_asset_missing_credentials():
    """Test get asset with missing credentials."""
    action = _make_action(
        GetAssetAction,
        credentials={"username": "", "password": ""},
    )
    result = await action.execute(hostname="srv-01")

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"


@pytest.mark.asyncio
async def test_get_asset_http_error(get_asset_action):
    """Test get asset with non-404 HTTP error."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"

    with patch.object(
        get_asset_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.HTTPStatusError(
            "Server Error",
            request=MagicMock(),
            response=mock_response,
        ),
    ):
        result = await get_asset_action.execute(hostname="srv-01")

    assert result["status"] == "error"
    assert result["error_type"] == "HTTPStatusError"
    assert result["integration_id"] == "exabeam"


@pytest.mark.asyncio
async def test_get_asset_timeout(get_asset_action):
    """Test get asset handles timeout."""
    with patch.object(
        get_asset_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.TimeoutException("Timeout"),
    ):
        result = await get_asset_action.execute(hostname="srv-01")

    assert result["status"] == "error"
    assert result["error_type"] == "TimeoutError"
