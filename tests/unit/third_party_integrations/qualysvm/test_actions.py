"""Unit tests for Qualys Vulnerability Management integration actions.

All actions use ``self.http_request()`` which applies
``integration_retry_policy`` automatically.  Tests mock at the
``IntegrationAction.http_request`` level.

Qualys returns XML responses, so mocked responses use ``.text`` with
XML strings rather than ``.json()``.
"""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from analysi.integrations.framework.integrations.qualysvm.actions import (
    HealthCheckAction,
    LaunchScanAction,
    ListAssetGroupsAction,
    ListHostFindingsAction,
    ScanSummaryAction,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Sample XML response bodies matching Qualys API format

AUTH_SUCCESS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<SIMPLE_RETURN>
  <RESPONSE>
    <DATETIME>2024-07-19T10:00:00Z</DATETIME>
    <TEXT>Logged in</TEXT>
  </RESPONSE>
</SIMPLE_RETURN>"""

ASSET_GROUPS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<ASSET_GROUP_LIST_OUTPUT>
  <RESPONSE>
    <ASSET_GROUP_LIST>
      <ASSET_GROUP>
        <ID>934333</ID>
        <TITLE>Test Group</TITLE>
        <NETWORK_ID>Default</NETWORK_ID>
        <IP_SET>
          <IP>8.8.8.8</IP>
          <IP_RANGE>1.1.1.1-1.1.1.3</IP_RANGE>
        </IP_SET>
      </ASSET_GROUP>
    </ASSET_GROUP_LIST>
  </RESPONSE>
</ASSET_GROUP_LIST_OUTPUT>"""

ASSET_GROUPS_PAGINATED_XML = """<?xml version="1.0" encoding="UTF-8"?>
<ASSET_GROUP_LIST_OUTPUT>
  <RESPONSE>
    <ASSET_GROUP_LIST>
      <ASSET_GROUP>
        <ID>100</ID>
        <TITLE>First Page</TITLE>
      </ASSET_GROUP>
    </ASSET_GROUP_LIST>
    <WARNING>
      <URL>/api/2.0/fo/asset/group/?action=list&amp;id_min=101</URL>
    </WARNING>
  </RESPONSE>
</ASSET_GROUP_LIST_OUTPUT>"""

ASSET_GROUPS_PAGE2_XML = """<?xml version="1.0" encoding="UTF-8"?>
<ASSET_GROUP_LIST_OUTPUT>
  <RESPONSE>
    <ASSET_GROUP_LIST>
      <ASSET_GROUP>
        <ID>101</ID>
        <TITLE>Second Page</TITLE>
      </ASSET_GROUP>
    </ASSET_GROUP_LIST>
  </RESPONSE>
</ASSET_GROUP_LIST_OUTPUT>"""

HOST_LIST_XML = """<?xml version="1.0" encoding="UTF-8"?>
<HOST_LIST_OUTPUT>
  <RESPONSE>
    <HOST_LIST>
      <HOST>
        <ID>1941672</ID>
        <ASSET_ID>2805388</ASSET_ID>
        <IP>172.217.22.14</IP>
        <DNS>fra16s14-in-f14.1e100.net</DNS>
        <TRACKING_METHOD>IP</TRACKING_METHOD>
        <OS>Linux 3.x</OS>
        <NETWORK_ID>Default</NETWORK_ID>
      </HOST>
    </HOST_LIST>
  </RESPONSE>
</HOST_LIST_OUTPUT>"""

HOST_ASSET_DETAILS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<ServiceResponse>
  <data>
    <HostAsset>
      <vuln>
        <list>
          <HostAssetVuln>
            <qid>70000</qid>
          </HostAssetVuln>
          <HostAssetVuln>
            <qid>70001</qid>
          </HostAssetVuln>
        </list>
      </vuln>
    </HostAsset>
  </data>
</ServiceResponse>"""

VULN_KB_XML = """<?xml version="1.0" encoding="UTF-8"?>
<KNOWLEDGE_BASE_VULN_LIST_OUTPUT>
  <RESPONSE>
    <VULN_LIST>
      <VULN>
        <QID>70000</QID>
        <VULN_TYPE>Information Gathered</VULN_TYPE>
        <SEVERITY_LEVEL>1</SEVERITY_LEVEL>
        <TITLE>Open TCP Services List</TITLE>
        <CATEGORY>TCP/IP</CATEGORY>
      </VULN>
      <VULN>
        <QID>70001</QID>
        <VULN_TYPE>Vulnerability</VULN_TYPE>
        <SEVERITY_LEVEL>3</SEVERITY_LEVEL>
        <TITLE>SSL Certificate Expiry</TITLE>
        <CATEGORY>General remote services</CATEGORY>
      </VULN>
    </VULN_LIST>
  </RESPONSE>
</KNOWLEDGE_BASE_VULN_LIST_OUTPUT>"""

LAUNCH_SCAN_SUCCESS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<SIMPLE_RETURN>
  <RESPONSE>
    <ITEM_LIST>
      <ITEM>
        <KEY>ID</KEY>
        <VALUE>994463</VALUE>
      </ITEM>
      <ITEM>
        <KEY>REFERENCE</KEY>
        <VALUE>scan/1658741010.01010</VALUE>
      </ITEM>
    </ITEM_LIST>
  </RESPONSE>
</SIMPLE_RETURN>"""

LAUNCH_SCAN_ERROR_XML = """<?xml version="1.0" encoding="UTF-8"?>
<SIMPLE_RETURN>
  <RESPONSE>
    <CODE>1905</CODE>
    <TEXT>IP(s) do not match the subscription</TEXT>
  </RESPONSE>
</SIMPLE_RETURN>"""

SCAN_SUMMARY_XML = """<?xml version="1.0" encoding="UTF-8"?>
<SCAN_SUMMARY_OUTPUT>
  <RESPONSE>
    <SCAN_SUMMARY_LIST>
      <SCAN_SUMMARY>
        <SCAN_REF>scan/1657784057.92367</SCAN_REF>
        <SCAN_DATE>2022-07-14T07:34:17Z</SCAN_DATE>
        <HOST_SUMMARY category="dead" tracking="IP">8.8.8.8</HOST_SUMMARY>
      </SCAN_SUMMARY>
    </SCAN_SUMMARY_LIST>
  </RESPONSE>
</SCAN_SUMMARY_OUTPUT>"""

SCAN_SUMMARY_EMPTY_XML = """<?xml version="1.0" encoding="UTF-8"?>
<SCAN_SUMMARY_OUTPUT>
  <RESPONSE>
  </RESPONSE>
</SCAN_SUMMARY_OUTPUT>"""

ERROR_XML = """<?xml version="1.0" encoding="UTF-8"?>
<SIMPLE_RETURN>
  <RESPONSE>
    <CODE>2000</CODE>
    <TEXT>Authentication failed</TEXT>
  </RESPONSE>
</SIMPLE_RETURN>"""


def _xml_response(text: str, status_code: int = 200) -> MagicMock:
    """Build a fake httpx.Response with XML text body."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.text = text
    resp.headers = {"Content-Type": "text/xml"}
    return resp


def _http_status_error(status_code: int, body: str = "") -> httpx.HTTPStatusError:
    """Build a fake HTTPStatusError with given status code and body."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = status_code
    mock_response.text = body or f"Error {status_code}"
    mock_request = MagicMock(spec=httpx.Request)
    return httpx.HTTPStatusError(
        message=f"HTTP {status_code}",
        request=mock_request,
        response=mock_response,
    )


_CREDS = {"username": "test-q-user", "password": "test-q-pass"}


def _make_action(action_class, credentials=None, settings=None):
    """Create an action instance with default test values."""
    return action_class(
        integration_id="qualysvm",
        action_id=action_class.__name__.lower().replace("action", ""),
        settings=settings if settings is not None else {},
        credentials=credentials if credentials is not None else dict(_CREDS),
    )


# ===========================================================================
# HealthCheckAction
# ===========================================================================


class TestHealthCheckAction:
    @pytest.fixture
    def action(self):
        return _make_action(HealthCheckAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        action.http_request = AsyncMock(return_value=_xml_response(AUTH_SUCCESS_XML))

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["healthy"] is True
        assert "integration_id" in result
        assert "timestamp" in result
        action.http_request.assert_called_once()

        # Verify basic auth is passed
        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["auth"] == ("test-q-user", "test-q-pass")

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(HealthCheckAction, credentials={})
        result = await action.execute()

        assert result["status"] == "error"
        assert "credentials" in result["error"].lower()
        assert result["error_type"] == "ConfigurationError"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_password(self):
        action = _make_action(
            HealthCheckAction, credentials={"username": "test-q-user"}
        )
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_http_error(self, action):
        action.http_request = AsyncMock(side_effect=_http_status_error(401, ERROR_XML))
        result = await action.execute()

        assert result["status"] == "error"
        assert result["data"]["healthy"] is False
        assert "Authentication failed" in result["error"]

    @pytest.mark.asyncio
    async def test_network_error(self, action):
        action.http_request = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        result = await action.execute()

        assert result["status"] == "error"
        assert result["data"]["healthy"] is False


# ===========================================================================
# ListAssetGroupsAction
# ===========================================================================


class TestListAssetGroupsAction:
    @pytest.fixture
    def action(self):
        return _make_action(ListAssetGroupsAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        action.http_request = AsyncMock(return_value=_xml_response(ASSET_GROUPS_XML))

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["found_asset_groups"] == 1
        groups = result["data"]["asset_groups"]
        assert len(groups) == 1
        assert groups[0]["ID"] == "934333"
        assert groups[0]["TITLE"] == "Test Group"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_ip_set_normalization(self, action):
        """IP and IP_RANGE should be wrapped as lists if they are strings."""
        action.http_request = AsyncMock(return_value=_xml_response(ASSET_GROUPS_XML))

        result = await action.execute()

        groups = result["data"]["asset_groups"]
        ip_set = groups[0]["IP_SET"]
        # xmltodict returns single values as strings; we normalize to lists
        assert isinstance(ip_set["IP"], list)
        assert isinstance(ip_set["IP_RANGE"], list)

    @pytest.mark.asyncio
    async def test_with_ids_filter(self, action):
        action.http_request = AsyncMock(return_value=_xml_response(ASSET_GROUPS_XML))

        result = await action.execute(ids="934333, 934334")

        assert result["status"] == "success"
        call_kwargs = action.http_request.call_args.kwargs
        assert "934333,934334" in call_kwargs["params"]["ids"]

    @pytest.mark.asyncio
    async def test_pagination(self, action):
        """Verify pagination follows WARNING/id_min links."""
        page1_resp = _xml_response(ASSET_GROUPS_PAGINATED_XML)
        page2_resp = _xml_response(ASSET_GROUPS_PAGE2_XML)
        action.http_request = AsyncMock(side_effect=[page1_resp, page2_resp])

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["found_asset_groups"] == 2
        assert action.http_request.call_count == 2

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(ListAssetGroupsAction, credentials={})
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_invalid_truncation_limit(self, action):
        result = await action.execute(truncation_limit="abc")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "truncation_limit" in result["error"]

    @pytest.mark.asyncio
    async def test_http_error(self, action):
        action.http_request = AsyncMock(side_effect=_http_status_error(500, ERROR_XML))

        result = await action.execute()

        assert result["status"] == "error"


# ===========================================================================
# ListHostFindingsAction
# ===========================================================================


class TestListHostFindingsAction:
    @pytest.fixture
    def action(self):
        return _make_action(ListHostFindingsAction)

    @pytest.mark.asyncio
    async def test_success_with_vulns(self, action):
        """Full flow: list hosts -> get asset info -> get vuln details."""
        host_resp = _xml_response(HOST_LIST_XML)
        asset_resp = _xml_response(HOST_ASSET_DETAILS_XML)
        vuln_resp = _xml_response(VULN_KB_XML)
        action.http_request = AsyncMock(side_effect=[host_resp, asset_resp, vuln_resp])

        result = await action.execute(ips="172.217.22.14")

        assert result["status"] == "success"
        assert result["data"]["found_hosts"] == 1

        host = result["data"]["hosts"][0]
        assert host["IP"] == "172.217.22.14"
        assert host["ASSET_ID"] == "2805388"
        assert len(host["VULN"]) == 2
        assert host["VULN"][0]["QID"] == "70000"
        assert host["VULN"][0]["TITLE"] == "Open TCP Services List"
        assert host["VULN"][1]["QID"] == "70001"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_no_hosts_found(self, action):
        empty_host_xml = """<?xml version="1.0" encoding="UTF-8"?>
<HOST_LIST_OUTPUT>
  <RESPONSE>
  </RESPONSE>
</HOST_LIST_OUTPUT>"""
        action.http_request = AsyncMock(return_value=_xml_response(empty_host_xml))

        result = await action.execute()

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["found_hosts"] == 0

    @pytest.mark.asyncio
    async def test_invalid_date_before(self, action):
        result = await action.execute(vm_scan_date_before="not-a-date")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "vm_scan_date_before" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_date_after(self, action):
        result = await action.execute(vm_scan_date_after="not-a-date")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "vm_scan_date_after" in result["error"]

    @pytest.mark.asyncio
    async def test_date_range_invalid(self, action):
        """after >= before should error."""
        result = await action.execute(
            vm_scan_date_before="2022-07-19T09:00:00Z",
            vm_scan_date_after="2022-07-19T10:00:00Z",
        )

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert (
            "earlier" in result["error"].lower()
            or "vm_scan_date_after" in result["error"]
        )

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(ListHostFindingsAction, credentials={})
        result = await action.execute(ips="8.8.8.8")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_http_error(self, action):
        action.http_request = AsyncMock(side_effect=_http_status_error(401, ERROR_XML))

        result = await action.execute(ips="8.8.8.8")

        assert result["status"] == "error"


# ===========================================================================
# LaunchScanAction
# ===========================================================================


class TestLaunchScanAction:
    @pytest.fixture
    def action(self):
        return _make_action(LaunchScanAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        action.http_request = AsyncMock(
            return_value=_xml_response(LAUNCH_SCAN_SUCCESS_XML)
        )

        result = await action.execute(
            option_title="Initial Options",
            ip="8.8.8.8",
            scan_title="Test Scan",
        )

        assert result["status"] == "success"
        assert result["data"]["message"] == "VM scan launched successfully"
        assert result["data"]["scan_response"] is not None
        assert "integration_id" in result

        # Verify POST method used
        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["method"] == "POST"

    @pytest.mark.asyncio
    async def test_missing_option_title(self, action):
        result = await action.execute(ip="8.8.8.8")

        assert result["status"] == "error"
        assert "option_title" in result["error"]
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(LaunchScanAction, credentials={})
        result = await action.execute(option_title="Initial Options")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_scan_error_in_xml(self, action):
        """Qualys returns 200 OK but SIMPLE_RETURN has error code instead of ITEM_LIST."""
        action.http_request = AsyncMock(
            return_value=_xml_response(LAUNCH_SCAN_ERROR_XML)
        )

        result = await action.execute(option_title="Initial Options", ip="8.8.8.8")

        assert result["status"] == "error"
        assert "1905" in result["error"] or "subscription" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_invalid_priority(self, action):
        result = await action.execute(option_title="Initial Options", priority="abc")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "priority" in result["error"]

    @pytest.mark.asyncio
    async def test_http_error(self, action):
        action.http_request = AsyncMock(side_effect=_http_status_error(500, ERROR_XML))

        result = await action.execute(option_title="Initial Options", ip="8.8.8.8")

        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_csv_params_cleaned(self, action):
        action.http_request = AsyncMock(
            return_value=_xml_response(LAUNCH_SCAN_SUCCESS_XML)
        )

        await action.execute(
            option_title="Initial Options",
            ip=" 8.8.8.8 , 1.1.1.1 ",
            asset_group_ids="100, 200, ",
        )

        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["params"]["ip"] == "8.8.8.8,1.1.1.1"
        assert call_kwargs["params"]["asset_group_ids"] == "100,200"


# ===========================================================================
# ScanSummaryAction
# ===========================================================================


class TestScanSummaryAction:
    @pytest.fixture
    def action(self):
        return _make_action(ScanSummaryAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        action.http_request = AsyncMock(return_value=_xml_response(SCAN_SUMMARY_XML))

        result = await action.execute(scan_date_since="2022-07-01")

        assert result["status"] == "success"
        assert result["data"]["found_scans"] == 1
        summary = result["data"]["scan_summaries"][0]
        assert summary["SCAN_REF"] == "scan/1657784057.92367"
        assert summary["HOST_SUMMARY"][0]["IP"] == "8.8.8.8"
        assert summary["HOST_SUMMARY"][0]["CATEGORY"] == "dead"
        assert summary["HOST_SUMMARY"][0]["TRACKING_METHOD"] == "IP"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_empty_results(self, action):
        action.http_request = AsyncMock(
            return_value=_xml_response(SCAN_SUMMARY_EMPTY_XML)
        )

        result = await action.execute(scan_date_since="2022-07-01")

        assert result["status"] == "success"
        assert result["data"]["found_scans"] == 0

    @pytest.mark.asyncio
    async def test_missing_scan_date_since(self, action):
        result = await action.execute()

        assert result["status"] == "error"
        assert "scan_date_since" in result["error"]
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_invalid_date_format(self, action):
        result = await action.execute(scan_date_since="July 2022")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "scan_date_since" in result["error"]

    @pytest.mark.asyncio
    async def test_date_range_invalid(self, action):
        result = await action.execute(
            scan_date_since="2022-07-20",
            scan_date_to="2022-07-19",
        )

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_no_include_params(self, action):
        """All include flags set to false should error."""
        result = await action.execute(
            scan_date_since="2022-07-01",
            include_dead=False,
            include_excluded=False,
            include_unresolved=False,
            include_cancelled=False,
            include_blocked=False,
            include_aborted=False,
        )

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "include" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(ScanSummaryAction, credentials={})
        result = await action.execute(scan_date_since="2022-07-01")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_http_error(self, action):
        action.http_request = AsyncMock(side_effect=_http_status_error(500, ERROR_XML))

        result = await action.execute(scan_date_since="2022-07-01")

        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_unparseable_xml(self, action):
        action.http_request = AsyncMock(return_value=_xml_response("not xml"))

        result = await action.execute(scan_date_since="2022-07-01")

        assert result["status"] == "error"
        assert result["error_type"] == "ParseError"


# ===========================================================================
# Base class helper tests
# ===========================================================================


class TestQualysBaseHelpers:
    """Test shared helper methods on the base class."""

    @pytest.fixture
    def action(self):
        return _make_action(HealthCheckAction)

    def test_get_base_url_default(self, action):
        url = action._get_base_url()
        assert url == "https://qualysapi.qualys.com"

    def test_get_base_url_custom(self):
        action = _make_action(
            HealthCheckAction,
            settings={"base_url": "https://qualysapi.eu.qualys.com/"},
        )
        url = action._get_base_url()
        assert url == "https://qualysapi.eu.qualys.com"

    def test_get_credentials(self, action):
        username, password = action._get_credentials()
        assert username == "test-q-user"
        assert password == "test-q-pass"

    def test_get_basic_auth(self, action):
        auth = action._get_basic_auth()
        assert auth == ("test-q-user", "test-q-pass")

    def test_get_basic_auth_missing(self):
        action = _make_action(HealthCheckAction, credentials={})
        auth = action._get_basic_auth()
        assert auth is None

    def test_parse_xml_valid(self, action):
        data = action._parse_xml(AUTH_SUCCESS_XML)
        assert data is not None
        assert "SIMPLE_RETURN" in data

    def test_parse_xml_invalid(self, action):
        data = action._parse_xml("not xml")
        assert data is None

    def test_extract_xml_error_success(self, action):
        detail = action._extract_xml_error(ERROR_XML)
        assert "2000" in detail
        assert "Authentication failed" in detail

    def test_extract_xml_error_invalid_xml(self, action):
        detail = action._extract_xml_error("not xml")
        assert detail == ""

    def test_validate_positive_int_valid(self, action):
        ok, val, err = action._validate_positive_int(100, "test")
        assert ok is True
        assert val == 100
        assert err == ""

    def test_validate_positive_int_none(self, action):
        ok, val, err = action._validate_positive_int(None, "test")
        assert ok is True
        assert val is None

    def test_validate_positive_int_negative(self, action):
        ok, val, err = action._validate_positive_int(-1, "test")
        assert ok is False
        assert "test" in err

    def test_validate_positive_int_string(self, action):
        ok, val, err = action._validate_positive_int("abc", "test")
        assert ok is False

    def test_validate_positive_int_float(self, action):
        ok, val, err = action._validate_positive_int(1.5, "test")
        assert ok is False

    def test_clean_csv(self, action):
        assert action._clean_csv(" a , b , c ") == "a,b,c"
        assert action._clean_csv("a,,b") == "a,b"
        assert action._clean_csv("") is None
        assert action._clean_csv(None) is None

    def test_get_timeout_default(self, action):
        assert action.get_timeout() == 30

    def test_get_timeout_custom(self):
        action = _make_action(HealthCheckAction, settings={"timeout": 60})
        assert action.get_timeout() == 60
