"""Unit tests for IBM QRadar integration actions.

Tests mock ``action.http_request`` (the framework helper), NOT raw httpx.
Each action class is tested for: success, missing params, missing creds,
and HTTP errors.
"""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from analysi.integrations.framework.integrations.qradar.actions import (
    AddNoteAction,
    AddToReferenceSetAction,
    AlertsToOcsfAction,
    AssignUserAction,
    CloseOffenseAction,
    GetEventsAction,
    GetFlowsAction,
    GetRuleInfoAction,
    HealthCheckAction,
    ListClosingReasonsAction,
    ListOffensesAction,
    ListRulesAction,
    OffenseDetailsAction,
    PullAlertsAction,
    RunQueryAction,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TOKEN_CREDS = {"auth_token": "test-sec-token"}
_BASIC_CREDS = {"username": "admin", "password": "secret"}
_SETTINGS = {"server": "qradar.example.com"}


def _json_response(data, status_code: int = 200) -> MagicMock:
    """Build a fake httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = data
    resp.text = str(data)
    return resp


def _http_status_error(status_code: int) -> httpx.HTTPStatusError:
    """Build an HTTPStatusError with the given status code."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.text = "error"
    request = MagicMock(spec=httpx.Request)
    return httpx.HTTPStatusError("error", request=request, response=resp)


def _make_action(cls, credentials=None, settings=None):
    """Create an action instance with default settings."""
    return cls(
        integration_id="qradar",
        action_id=cls.__name__.lower().replace("action", ""),
        settings=_SETTINGS if settings is None else settings,
        credentials=_TOKEN_CREDS if credentials is None else credentials,
    )


# ===========================================================================
# HealthCheckAction
# ===========================================================================


class TestHealthCheckAction:
    @pytest.mark.asyncio
    async def test_success(self):
        action = _make_action(HealthCheckAction)
        action.http_request = AsyncMock(
            return_value=_json_response(["events", "flows", "siem"])
        )

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["healthy"] is True
        assert result["data"]["databases"] == ["events", "flows", "siem"]
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(HealthCheckAction, credentials={})
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_missing_server(self):
        action = _make_action(HealthCheckAction, settings={"server": ""})
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_connection_error(self):
        action = _make_action(HealthCheckAction)
        action.http_request = AsyncMock(side_effect=httpx.ConnectError("refused"))

        result = await action.execute()

        assert result["status"] == "error"
        assert result["data"]["healthy"] is False


# ===========================================================================
# ListOffensesAction
# ===========================================================================


class TestListOffensesAction:
    @pytest.mark.asyncio
    async def test_success_default(self):
        action = _make_action(ListOffensesAction)
        offenses = [{"id": 1, "description": "test offense"}]
        action.http_request = AsyncMock(return_value=_json_response(offenses))

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["total_offenses"] == 1
        assert result["data"]["offenses"] == offenses
        action.http_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_success_with_offense_ids(self):
        action = _make_action(ListOffensesAction)
        offenses = [{"id": 1}, {"id": 2}]
        action.http_request = AsyncMock(return_value=_json_response(offenses))

        result = await action.execute(offense_id="1,2")

        assert result["status"] == "success"
        assert result["data"]["total_offenses"] == 2
        # Verify filter contains the IDs
        call_kwargs = action.http_request.call_args
        assert "id=1" in call_kwargs.kwargs["params"]["filter"]
        assert "id=2" in call_kwargs.kwargs["params"]["filter"]

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(ListOffensesAction, credentials={})
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_http_error(self):
        action = _make_action(ListOffensesAction)
        action.http_request = AsyncMock(side_effect=_http_status_error(500))

        result = await action.execute()

        assert result["status"] == "error"


# ===========================================================================
# OffenseDetailsAction
# ===========================================================================


class TestOffenseDetailsAction:
    @pytest.mark.asyncio
    async def test_success(self):
        action = _make_action(OffenseDetailsAction)
        offense = {
            "id": 44,
            "description": "Test offense",
            "status": "OPEN",
            "severity": 7,
        }
        action.http_request = AsyncMock(return_value=_json_response(offense))

        result = await action.execute(offense_id="44")

        assert result["status"] == "success"
        assert result["data"]["id"] == 44

    @pytest.mark.asyncio
    async def test_missing_offense_id(self):
        action = _make_action(OffenseDetailsAction)
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_not_found(self):
        action = _make_action(OffenseDetailsAction)
        action.http_request = AsyncMock(side_effect=_http_status_error(404))

        result = await action.execute(offense_id="99999")

        assert result["status"] == "success"
        assert result["not_found"] is True

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(OffenseDetailsAction, credentials={})
        result = await action.execute(offense_id="44")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


# ===========================================================================
# CloseOffenseAction
# ===========================================================================


class TestCloseOffenseAction:
    @pytest.mark.asyncio
    async def test_success(self):
        action = _make_action(CloseOffenseAction)
        closed = {"id": 44, "status": "CLOSED", "closing_reason_id": 1}
        action.http_request = AsyncMock(return_value=_json_response(closed))

        result = await action.execute(offense_id="44", closing_reason_id=1)

        assert result["status"] == "success"
        assert result["data"]["status"] == "CLOSED"

    @pytest.mark.asyncio
    async def test_missing_offense_id(self):
        action = _make_action(CloseOffenseAction)
        result = await action.execute(closing_reason_id=1)

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_closing_reason_id(self):
        action = _make_action(CloseOffenseAction)
        result = await action.execute(offense_id="44")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(CloseOffenseAction, credentials={})
        result = await action.execute(offense_id="44", closing_reason_id=1)

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


# ===========================================================================
# AddNoteAction
# ===========================================================================


class TestAddNoteAction:
    @pytest.mark.asyncio
    async def test_success(self):
        action = _make_action(AddNoteAction)
        action.http_request = AsyncMock(
            return_value=_json_response({"note_text": "test note"})
        )

        result = await action.execute(offense_id="44", note_text="test note")

        assert result["status"] == "success"
        assert result["data"]["message"] == "Note added successfully"

    @pytest.mark.asyncio
    async def test_missing_offense_id(self):
        action = _make_action(AddNoteAction)
        result = await action.execute(note_text="test")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_note_text(self):
        action = _make_action(AddNoteAction)
        result = await action.execute(offense_id="44")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(AddNoteAction, credentials={})
        result = await action.execute(offense_id="44", note_text="note")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


# ===========================================================================
# AssignUserAction
# ===========================================================================


class TestAssignUserAction:
    @pytest.mark.asyncio
    async def test_success(self):
        action = _make_action(AssignUserAction)
        resp = {"id": 44, "assigned_to": "admin"}
        action.http_request = AsyncMock(return_value=_json_response(resp))

        result = await action.execute(offense_id="44", assignee="admin")

        assert result["status"] == "success"
        assert result["data"]["assigned_to"] == "admin"

    @pytest.mark.asyncio
    async def test_missing_offense_id(self):
        action = _make_action(AssignUserAction)
        result = await action.execute(assignee="admin")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_assignee(self):
        action = _make_action(AssignUserAction)
        result = await action.execute(offense_id="44")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"


# ===========================================================================
# ListClosingReasonsAction
# ===========================================================================


class TestListClosingReasonsAction:
    @pytest.mark.asyncio
    async def test_success(self):
        action = _make_action(ListClosingReasonsAction)
        reasons = [
            {"id": 1, "text": "False-Positive, Tuned"},
            {"id": 2, "text": "Non-Issue"},
        ]
        action.http_request = AsyncMock(return_value=_json_response(reasons))

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["total_closing_reasons"] == 2

    @pytest.mark.asyncio
    async def test_with_include_reserved(self):
        action = _make_action(ListClosingReasonsAction)
        action.http_request = AsyncMock(return_value=_json_response([]))

        await action.execute(include_reserved=True, include_deleted=True)

        call_kwargs = action.http_request.call_args
        assert call_kwargs.kwargs["params"]["include_reserved"] is True
        assert call_kwargs.kwargs["params"]["include_deleted"] is True

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(ListClosingReasonsAction, credentials={})
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


# ===========================================================================
# GetEventsAction
# ===========================================================================


class TestGetEventsAction:
    @pytest.mark.asyncio
    async def test_success(self, monkeypatch):
        action = _make_action(GetEventsAction)
        # Ariel query requires 3 HTTP calls: POST search, GET status, GET results
        submit_resp = _json_response({"search_id": "abc-123", "status": "EXECUTE"})
        status_resp = _json_response(
            {"search_id": "abc-123", "status": "COMPLETED", "progress": 100}
        )
        results_resp = _json_response(
            {"events": [{"sourceip": "10.0.0.1", "qid": 123}]}
        )

        call_count = 0
        responses = [submit_resp, status_resp, results_resp]

        async def mock_request(*args, **kwargs):
            nonlocal call_count
            resp = responses[min(call_count, len(responses) - 1)]
            call_count += 1
            return resp

        action.http_request = AsyncMock(side_effect=mock_request)
        # Speed up the ariel poll sleep
        monkeypatch.setattr("asyncio.sleep", AsyncMock())

        result = await action.execute(offense_id=44, count=10)

        assert result["status"] == "success"
        assert result["data"]["total_events"] == 1

    @pytest.mark.asyncio
    async def test_transient_503_during_polling_recovers(self, monkeypatch):
        """A transient 503 during Ariel status polling should not kill the query.

        The polling loop must absorb transient HTTP errors and continue polling
        rather than letting the exception propagate and losing the search_id.
        """
        action = _make_action(GetEventsAction)
        submit_resp = _json_response({"search_id": "evt-503", "status": "EXECUTE"})
        status_503 = MagicMock()
        status_503.status_code = 503
        completed_resp = _json_response(
            {"search_id": "evt-503", "status": "COMPLETED", "progress": 100}
        )
        results_resp = _json_response({"events": [{"category": "test"}]})

        call_count = 0
        responses = [submit_resp, status_503, completed_resp, results_resp]

        async def mock_request(*args, **kwargs):
            nonlocal call_count
            resp = responses[min(call_count, len(responses) - 1)]
            call_count += 1
            if hasattr(resp, "status_code") and resp.status_code == 503:
                raise httpx.HTTPStatusError(
                    "Service Unavailable",
                    request=MagicMock(spec=httpx.Request),
                    response=resp,
                )
            return resp

        action.http_request = AsyncMock(side_effect=mock_request)
        monkeypatch.setattr("asyncio.sleep", AsyncMock())

        result = await action.execute(offense_id=44, count=10)

        # Should succeed — the 503 was absorbed and polling continued
        assert result["status"] == "success"
        assert result["data"]["total_events"] == 1

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(GetEventsAction, credentials={})
        result = await action.execute(offense_id=44)

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


# ===========================================================================
# GetFlowsAction
# ===========================================================================


class TestGetFlowsAction:
    @pytest.mark.asyncio
    async def test_success(self, monkeypatch):
        action = _make_action(GetFlowsAction)
        submit_resp = _json_response({"search_id": "flow-1", "status": "EXECUTE"})
        status_resp = _json_response(
            {"search_id": "flow-1", "status": "COMPLETED", "progress": 100}
        )
        results_resp = _json_response(
            {"flows": [{"sourceip": "10.0.0.1", "destinationip": "10.0.0.2"}]}
        )

        call_count = 0
        responses = [submit_resp, status_resp, results_resp]

        async def mock_request(*args, **kwargs):
            nonlocal call_count
            resp = responses[min(call_count, len(responses) - 1)]
            call_count += 1
            return resp

        action.http_request = AsyncMock(side_effect=mock_request)
        monkeypatch.setattr("asyncio.sleep", AsyncMock())

        result = await action.execute(offense_id=44)

        assert result["status"] == "success"
        assert result["data"]["total_flows"] == 1

    @pytest.mark.asyncio
    async def test_missing_ip_and_offense_id(self):
        action = _make_action(GetFlowsAction)
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(GetFlowsAction, credentials={})
        result = await action.execute(ip="10.0.0.1")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


# ===========================================================================
# RunQueryAction
# ===========================================================================


class TestRunQueryAction:
    @pytest.mark.asyncio
    async def test_success(self, monkeypatch):
        action = _make_action(RunQueryAction)
        submit_resp = _json_response({"search_id": "q-1", "status": "EXECUTE"})
        status_resp = _json_response(
            {"search_id": "q-1", "status": "COMPLETED", "progress": 100}
        )
        results_resp = _json_response({"events": [{"count": 42}]})

        call_count = 0
        responses = [submit_resp, status_resp, results_resp]

        async def mock_request(*args, **kwargs):
            nonlocal call_count
            resp = responses[min(call_count, len(responses) - 1)]
            call_count += 1
            return resp

        action.http_request = AsyncMock(side_effect=mock_request)
        monkeypatch.setattr("asyncio.sleep", AsyncMock())

        result = await action.execute(query="select count(*) from events last 1 hours")

        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_missing_query(self):
        action = _make_action(RunQueryAction)
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(RunQueryAction, credentials={})
        result = await action.execute(query="select 1")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


# ===========================================================================
# GetRuleInfoAction
# ===========================================================================


class TestGetRuleInfoAction:
    @pytest.mark.asyncio
    async def test_success(self):
        action = _make_action(GetRuleInfoAction)
        rule = {"id": 100, "name": "High Severity", "type": "EVENT"}
        action.http_request = AsyncMock(return_value=_json_response(rule))

        result = await action.execute(rule_id="100")

        assert result["status"] == "success"
        assert result["data"]["id"] == 100

    @pytest.mark.asyncio
    async def test_missing_rule_id(self):
        action = _make_action(GetRuleInfoAction)
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_not_found(self):
        action = _make_action(GetRuleInfoAction)
        action.http_request = AsyncMock(side_effect=_http_status_error(404))

        result = await action.execute(rule_id="99999")

        assert result["status"] == "success"
        assert result["not_found"] is True

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(GetRuleInfoAction, credentials={})
        result = await action.execute(rule_id="100")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


# ===========================================================================
# ListRulesAction
# ===========================================================================


class TestListRulesAction:
    @pytest.mark.asyncio
    async def test_success(self):
        action = _make_action(ListRulesAction)
        rules = [{"id": 1, "name": "Rule A"}, {"id": 2, "name": "Rule B"}]
        action.http_request = AsyncMock(return_value=_json_response(rules))

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["total_rules"] == 2

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(ListRulesAction, credentials={})
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


# ===========================================================================
# AddToReferenceSetAction
# ===========================================================================


class TestAddToReferenceSetAction:
    @pytest.mark.asyncio
    async def test_success(self):
        action = _make_action(AddToReferenceSetAction)
        resp = {
            "name": "blocked_ips",
            "element_type": "IP",
            "number_of_elements": 5,
        }
        action.http_request = AsyncMock(return_value=_json_response(resp))

        result = await action.execute(
            reference_set_name="blocked_ips",
            reference_set_value="10.0.0.1",
        )

        assert result["status"] == "success"
        assert result["data"]["name"] == "blocked_ips"

    @pytest.mark.asyncio
    async def test_missing_name(self):
        action = _make_action(AddToReferenceSetAction)
        result = await action.execute(reference_set_value="10.0.0.1")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_value(self):
        action = _make_action(AddToReferenceSetAction)
        result = await action.execute(reference_set_name="blocked_ips")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(AddToReferenceSetAction, credentials={})
        result = await action.execute(
            reference_set_name="blocked_ips",
            reference_set_value="10.0.0.1",
        )

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


# ===========================================================================
# Auth header tests (_QRadarBase)
# ===========================================================================


class TestQRadarBaseAuth:
    """Test that the base class generates correct auth headers."""

    @pytest.mark.asyncio
    async def test_sec_token_header(self):
        action = _make_action(
            HealthCheckAction,
            credentials={"auth_token": "my-token"},
        )
        headers = action.get_http_headers()
        assert headers["SEC"] == "my-token"
        assert "Authorization" not in headers

    @pytest.mark.asyncio
    async def test_basic_auth_header(self):
        action = _make_action(
            HealthCheckAction,
            credentials={"username": "admin", "password": "pass123"},
        )
        headers = action.get_http_headers()
        assert "Authorization" in headers
        assert headers["Authorization"].startswith("Basic ")
        assert "SEC" not in headers

    @pytest.mark.asyncio
    async def test_empty_credentials_headers(self):
        action = _make_action(HealthCheckAction, credentials={})
        headers = action.get_http_headers()
        # Should still have Accept but no auth
        assert headers.get("Accept") == "application/json"
        assert "SEC" not in headers
        assert "Authorization" not in headers

    @pytest.mark.asyncio
    async def test_base_url_construction(self):
        action = _make_action(
            HealthCheckAction,
            settings={"server": "10.0.0.1"},
        )
        assert action._base_url() == "https://10.0.0.1/api/"

    @pytest.mark.asyncio
    async def test_base_url_with_scheme(self):
        action = _make_action(
            HealthCheckAction,
            settings={"server": "https://qradar.corp.com"},
        )
        assert action._base_url() == "https://qradar.corp.com/api/"


# ===========================================================================
# PullAlertsAction
# ===========================================================================


class TestPullAlertsAction:
    @pytest.mark.asyncio
    async def test_success_default_lookback(self):
        action = _make_action(PullAlertsAction)
        offenses = [
            {"id": 1, "description": "test offense", "severity": 5},
            {"id": 2, "description": "another offense", "severity": 8},
        ]
        action.http_request = AsyncMock(return_value=_json_response(offenses))

        result = await action.execute()

        assert result["status"] == "success"
        assert result["alerts_count"] == 2
        assert result["alerts"] == offenses
        assert "Retrieved 2 offenses" in result["message"]

        # Verify the API was called with correct endpoint and filter
        call_kwargs = action.http_request.call_args
        assert "siem/offenses" in call_kwargs.kwargs.get(
            "url", call_kwargs.args[0] if call_kwargs.args else ""
        )
        assert "start_time" in call_kwargs.kwargs["params"]["filter"]

    @pytest.mark.asyncio
    async def test_success_with_time_range(self):
        action = _make_action(PullAlertsAction)
        offenses = [{"id": 10, "severity": 3}]
        action.http_request = AsyncMock(return_value=_json_response(offenses))

        result = await action.execute(
            start_time="2025-03-15T10:00:00+00:00",
            end_time="2025-03-15T11:00:00+00:00",
        )

        assert result["status"] == "success"
        assert result["alerts_count"] == 1

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(PullAlertsAction, credentials={})
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"
        assert result["alerts_count"] == 0
        assert result["alerts"] == []

    @pytest.mark.asyncio
    async def test_missing_server(self):
        action = _make_action(PullAlertsAction, settings={"server": ""})
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"
        assert result["alerts_count"] == 0

    @pytest.mark.asyncio
    async def test_http_error(self):
        action = _make_action(PullAlertsAction)
        action.http_request = AsyncMock(side_effect=_http_status_error(500))

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "HTTPError"
        assert result["alerts_count"] == 0
        assert result["alerts"] == []

    @pytest.mark.asyncio
    async def test_connection_error(self):
        action = _make_action(PullAlertsAction)
        action.http_request = AsyncMock(side_effect=httpx.ConnectError("refused"))

        result = await action.execute()

        assert result["status"] == "error"
        assert result["alerts_count"] == 0

    @pytest.mark.asyncio
    async def test_empty_response(self):
        action = _make_action(PullAlertsAction)
        action.http_request = AsyncMock(return_value=_json_response([]))

        result = await action.execute()

        assert result["status"] == "success"
        assert result["alerts_count"] == 0
        assert result["alerts"] == []

    @pytest.mark.asyncio
    async def test_max_results_sets_range_header(self):
        action = _make_action(PullAlertsAction)
        action.http_request = AsyncMock(return_value=_json_response([]))

        await action.execute(max_results=50)

        call_kwargs = action.http_request.call_args
        assert call_kwargs.kwargs["headers"]["Range"] == "items=0-49"


# ===========================================================================
# AlertsToOcsfAction
# ===========================================================================


class TestAlertsToOcsfAction:
    @pytest.mark.asyncio
    async def test_success_normalizes_offenses(self):
        action = _make_action(AlertsToOcsfAction)
        raw_offenses = [
            {
                "id": 42,
                "description": "Multiple Login Failures",
                "offense_type_str": "Source IP",
                "offense_source": "10.0.0.55",
                "severity": 6,
                "magnitude": 7,
                "status": "OPEN",
                "categories": ["Authentication"],
                "start_time": 1710500000000,
                "last_updated_time": 1710503600000,
            },
        ]

        result = await action.execute(raw_alerts=raw_offenses)

        assert result["status"] == "success"
        assert result["count"] == 1
        assert result["errors"] == 0
        ocsf = result["normalized_alerts"][0]
        assert ocsf["class_uid"] == 2004
        assert ocsf["severity_id"] == 4  # severity 6 -> High
        assert ocsf["is_alert"] is True
        assert ocsf["message"] == "Multiple Login Failures"

    @pytest.mark.asyncio
    async def test_empty_alerts(self):
        action = _make_action(AlertsToOcsfAction)

        result = await action.execute(raw_alerts=[])

        assert result["status"] == "success"
        assert result["count"] == 0
        assert result["errors"] == 0
        assert result["normalized_alerts"] == []

    @pytest.mark.asyncio
    async def test_no_raw_alerts_param(self):
        action = _make_action(AlertsToOcsfAction)

        result = await action.execute()

        assert result["status"] == "success"
        assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_multiple_offenses(self):
        action = _make_action(AlertsToOcsfAction)
        raw_offenses = [
            {
                "id": 1,
                "description": "Offense A",
                "severity": 2,
                "status": "OPEN",
                "start_time": 1710400000000,
            },
            {
                "id": 2,
                "description": "Offense B",
                "severity": 9,
                "status": "CLOSED",
                "start_time": 1710500000000,
            },
        ]

        result = await action.execute(raw_alerts=raw_offenses)

        assert result["count"] == 2
        assert result["errors"] == 0
        # Verify severity mapping
        assert result["normalized_alerts"][0]["severity"] == "Low"
        assert result["normalized_alerts"][1]["severity"] == "Critical"
        # Verify status mapping
        assert result["normalized_alerts"][0]["status"] == "New"
        assert result["normalized_alerts"][1]["status"] == "Closed"

    @pytest.mark.asyncio
    async def test_partial_failure(self):
        """If one offense fails normalization, others still succeed."""
        action = _make_action(AlertsToOcsfAction)
        raw_offenses = [
            {
                "id": 1,
                "description": "Good offense",
                "severity": 5,
                "status": "OPEN",
                "start_time": 1710400000000,
            },
            "not a dict",  # This will fail normalization
        ]

        result = await action.execute(raw_alerts=raw_offenses)

        assert result["status"] == "partial"
        assert result["count"] == 1
        assert result["errors"] == 1
