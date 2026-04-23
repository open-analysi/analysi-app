"""
Unit tests for CyOCSFHelpers.

Each helper is tested with OCSF-shaped and empty/missing-field alert dicts.
"""

import re
from pathlib import Path

import pytest

from analysi.services.cy_ocsf_helpers import (
    OCSF_TYPE_ID_TO_NAME,
    OCSF_TYPE_ID_TO_SHORT,
    SHORT_TO_OCSF_TYPE_ID,
    CyOCSFHelpers,
    create_cy_ocsf_helpers,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def ocsf_alert() -> dict:
    """Sample OCSF-shaped alert."""
    return {
        "finding_info": {"title": "SQL Injection Detected", "uid": "alert-001"},
        "severity_id": 4,
        "severity": "High",
        "metadata": {
            "product": {"vendor_name": "Splunk", "name": "Enterprise Security"},
            "labels": ["source_category:Firewall"],
            "version": "1.8.0",
        },
        "actor": {"user": {"name": "jdoe", "uid": "jdoe"}},
        "device": {"hostname": "ws-001", "ip": "10.0.1.50"},
        "observables": [
            {"type_id": 2, "type": "IP Address", "value": "203.0.113.50"},
            {"type_id": 1, "type": "Hostname", "value": "evil.example.com"},
        ],
        "evidences": [
            {
                "src_endpoint": {"ip": "203.0.113.50"},
                "dst_endpoint": {
                    "ip": "10.0.1.100",
                    "port": 443,
                    "domain": "internal.corp.com",
                },
                "url": {"url_string": "https://example.com/api", "path": "/api"},
                "http_request": {
                    "http_method": "POST",
                    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                },
                "http_response": {"code": 403},
            }
        ],
        "vulnerabilities": [
            {"cve": {"uid": "CVE-2022-41082"}},
            {"cve": {"uid": "CVE-2022-41040"}},
        ],
    }


@pytest.fixture
def helpers() -> CyOCSFHelpers:
    return CyOCSFHelpers()


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_ocsf_type_id_to_name_has_expected_entries(self):
        assert OCSF_TYPE_ID_TO_NAME[2] == "IP Address"
        assert OCSF_TYPE_ID_TO_NAME[1] == "Hostname"
        assert OCSF_TYPE_ID_TO_NAME[7] == "File Name"

    def test_ocsf_type_id_to_short_has_expected_entries(self):
        assert OCSF_TYPE_ID_TO_SHORT[2] == "ip"
        assert OCSF_TYPE_ID_TO_SHORT[1] == "domain"
        assert OCSF_TYPE_ID_TO_SHORT[6] == "url"

    def test_short_to_ocsf_type_id_reverse_mapping(self):
        assert SHORT_TO_OCSF_TYPE_ID["ip"] == 2
        assert SHORT_TO_OCSF_TYPE_ID["domain"] == 1
        assert SHORT_TO_OCSF_TYPE_ID["url"] == 6


# ---------------------------------------------------------------------------
# get_primary_entity_type
# ---------------------------------------------------------------------------


class TestGetPrimaryEntityType:
    def test_get_primary_entity_type_ocsf(self, helpers, ocsf_alert):
        assert helpers.get_primary_entity_type(ocsf_alert) == "user"

    def test_get_primary_entity_type_ocsf_device_only(self, helpers):
        alert = {"device": {"hostname": "srv-01"}}
        assert helpers.get_primary_entity_type(alert) == "device"

    def test_get_primary_entity_type_user_takes_precedence_over_device(self, helpers):
        alert = {
            "actor": {"user": {"name": "jdoe"}},
            "device": {"hostname": "srv-01"},
        }
        assert helpers.get_primary_entity_type(alert) == "user"

    def test_get_primary_entity_type_empty(self, helpers):
        assert helpers.get_primary_entity_type({}) is None


# ---------------------------------------------------------------------------
# get_primary_entity_value
# ---------------------------------------------------------------------------


class TestGetPrimaryEntityValue:
    def test_get_primary_entity_value_ocsf(self, helpers, ocsf_alert):
        assert helpers.get_primary_entity_value(ocsf_alert) == "jdoe"

    def test_get_primary_entity_value_ocsf_uid_fallback(self, helpers):
        alert = {"actor": {"user": {"uid": "u-123"}}}
        assert helpers.get_primary_entity_value(alert) == "u-123"

    def test_get_primary_entity_value_ocsf_device_fallback(self, helpers):
        alert = {"device": {"hostname": "srv-01"}}
        assert helpers.get_primary_entity_value(alert) == "srv-01"

    def test_get_primary_entity_value_ocsf_device_ip_fallback(self, helpers):
        alert = {"device": {"ip": "10.0.0.1"}}
        assert helpers.get_primary_entity_value(alert) == "10.0.0.1"

    def test_get_primary_entity_value_user_takes_precedence_over_device(self, helpers):
        alert = {
            "actor": {"user": {"name": "alice"}},
            "device": {"hostname": "srv-01"},
        }
        assert helpers.get_primary_entity_value(alert) == "alice"

    def test_get_primary_entity_value_empty(self, helpers):
        assert helpers.get_primary_entity_value({}) is None


# ---------------------------------------------------------------------------
# get_primary_user
# ---------------------------------------------------------------------------


class TestGetPrimaryUser:
    def test_get_primary_user_ocsf(self, helpers, ocsf_alert):
        assert helpers.get_primary_user(ocsf_alert) == "jdoe"

    def test_get_primary_user_ocsf_uid_fallback(self, helpers):
        alert = {"actor": {"user": {"uid": "u-123"}}}
        assert helpers.get_primary_user(alert) == "u-123"

    def test_get_primary_user_no_actor(self, helpers):
        alert = {"device": {"hostname": "srv-01"}}
        assert helpers.get_primary_user(alert) is None

    def test_get_primary_user_empty(self, helpers):
        assert helpers.get_primary_user({}) is None


# ---------------------------------------------------------------------------
# get_primary_device
# ---------------------------------------------------------------------------


class TestGetPrimaryDevice:
    def test_get_primary_device_ocsf(self, helpers, ocsf_alert):
        assert helpers.get_primary_device(ocsf_alert) == "ws-001"

    def test_get_primary_device_ocsf_name_fallback(self, helpers):
        alert = {"device": {"name": "laptop-42"}}
        assert helpers.get_primary_device(alert) == "laptop-42"

    def test_get_primary_device_ocsf_ip_fallback(self, helpers):
        alert = {"device": {"ip": "10.0.0.5"}}
        assert helpers.get_primary_device(alert) == "10.0.0.5"

    def test_get_primary_device_no_device(self, helpers):
        alert = {"actor": {"user": {"name": "jdoe"}}}
        assert helpers.get_primary_device(alert) is None

    def test_get_primary_device_empty(self, helpers):
        assert helpers.get_primary_device({}) is None


# ---------------------------------------------------------------------------
# get_primary_observable_type
# ---------------------------------------------------------------------------


class TestGetPrimaryObservableType:
    def test_get_primary_observable_type_ocsf(self, helpers, ocsf_alert):
        # Must return short name even when OCSF observable has verbose "IP Address"
        assert helpers.get_primary_observable_type(ocsf_alert) == "ip"

    def test_get_primary_observable_type_unmapped_type_id(self, helpers):
        alert = {"observables": [{"type_id": 999, "value": "something"}]}
        assert helpers.get_primary_observable_type(alert) == "Unknown(999)"

    def test_get_primary_observable_type_empty(self, helpers):
        assert helpers.get_primary_observable_type({}) is None

    def test_get_primary_observable_type_ocsf_empty_observables(self, helpers):
        assert helpers.get_primary_observable_type({"observables": []}) is None


# ---------------------------------------------------------------------------
# get_primary_observable_value
# ---------------------------------------------------------------------------


class TestGetPrimaryObservableValue:
    def test_get_primary_observable_value_ocsf(self, helpers, ocsf_alert):
        assert helpers.get_primary_observable_value(ocsf_alert) == "203.0.113.50"

    def test_get_primary_observable_value_empty(self, helpers):
        assert helpers.get_primary_observable_value({}) is None

    def test_get_primary_observable_value_empty_observables(self, helpers):
        assert helpers.get_primary_observable_value({"observables": []}) is None


# ---------------------------------------------------------------------------
# get_primary_observable
# ---------------------------------------------------------------------------


class TestGetPrimaryObservable:
    def test_get_primary_observable_ocsf_no_type(self, helpers, ocsf_alert):
        result = helpers.get_primary_observable(ocsf_alert)
        assert result is not None
        assert result["value"] == "203.0.113.50"
        # Must return short name even from OCSF observable
        assert result["type"] == "ip"

    def test_get_primary_observable_ocsf_matching_type(self, helpers, ocsf_alert):
        # Both short name "ip" and OCSF verbose "IP Address" should match
        result = helpers.get_primary_observable(ocsf_alert, type="ip")
        assert result is not None
        assert result["value"] == "203.0.113.50"

    def test_get_primary_observable_ocsf_by_short_name(self, helpers, ocsf_alert):
        """Short name 'ip' should match OCSF type_id=2."""
        result = helpers.get_primary_observable(ocsf_alert, type="ip")
        assert result is not None
        assert result["value"] == "203.0.113.50"

    def test_get_primary_observable_ocsf_by_domain(self, helpers, ocsf_alert):
        result = helpers.get_primary_observable(ocsf_alert, type="domain")
        assert result is not None
        assert result["type"] == "domain"
        assert result["value"] == "evil.example.com"

    def test_get_primary_observable_ocsf_missing_type(self, helpers, ocsf_alert):
        result = helpers.get_primary_observable(ocsf_alert, type="filehash")
        assert result is None

    def test_get_primary_observable_empty(self, helpers):
        assert helpers.get_primary_observable({}) is None


# ---------------------------------------------------------------------------
# get_observables
# ---------------------------------------------------------------------------


class TestGetObservables:
    def test_get_observables_ocsf_all(self, helpers, ocsf_alert):
        result = helpers.get_observables(ocsf_alert)
        assert len(result) == 2
        assert result[0]["value"] == "203.0.113.50"
        # Must return short name even from OCSF observable
        assert result[0]["type"] == "ip"

    def test_get_observables_ocsf_filtered_by_name(self, helpers, ocsf_alert):
        result = helpers.get_observables(ocsf_alert, type="domain")
        assert len(result) == 1
        assert result[0]["value"] == "evil.example.com"

    def test_get_observables_ocsf_filtered_by_short_name(self, helpers, ocsf_alert):
        """Short name 'ip' maps to OCSF type_id=2, so should match."""
        result = helpers.get_observables(ocsf_alert, type="ip")
        assert len(result) == 1
        assert result[0]["value"] == "203.0.113.50"

    def test_get_observables_ocsf_filter_no_match(self, helpers, ocsf_alert):
        result = helpers.get_observables(ocsf_alert, type="filehash")
        assert result == []

    def test_get_observables_empty(self, helpers):
        assert helpers.get_observables({}) == []

    def test_get_observables_returns_dicts_with_type_and_value(
        self, helpers, ocsf_alert
    ):
        for obs in helpers.get_observables(ocsf_alert):
            assert "type" in obs
            assert "value" in obs


# ---------------------------------------------------------------------------
# get_src_ip
# ---------------------------------------------------------------------------


class TestGetSrcIp:
    def test_get_src_ip_ocsf(self, helpers, ocsf_alert):
        assert helpers.get_src_ip(ocsf_alert) == "203.0.113.50"

    def test_get_src_ip_empty(self, helpers):
        assert helpers.get_src_ip({}) is None

    def test_get_src_ip_ocsf_no_src_endpoint(self, helpers):
        alert = {"evidences": [{"dst_endpoint": {"ip": "1.2.3.4"}}]}
        assert helpers.get_src_ip(alert) is None

    def test_get_src_ip_multiple_evidences(self, helpers):
        alert = {
            "evidences": [
                {"dst_endpoint": {"ip": "10.0.0.1"}},
                {"src_endpoint": {"ip": "192.168.1.1"}},
            ]
        }
        assert helpers.get_src_ip(alert) == "192.168.1.1"


# ---------------------------------------------------------------------------
# get_dst_ip
# ---------------------------------------------------------------------------


class TestGetDstIp:
    def test_get_dst_ip_ocsf(self, helpers, ocsf_alert):
        assert helpers.get_dst_ip(ocsf_alert) == "10.0.1.100"

    def test_get_dst_ip_empty(self, helpers):
        assert helpers.get_dst_ip({}) is None

    def test_get_dst_ip_ocsf_no_dst_endpoint(self, helpers):
        alert = {"evidences": [{"src_endpoint": {"ip": "1.2.3.4"}}]}
        assert helpers.get_dst_ip(alert) is None

    def test_get_dst_ip_multiple_evidences(self, helpers):
        alert = {
            "evidences": [
                {"src_endpoint": {"ip": "10.0.0.1"}},
                {"dst_endpoint": {"ip": "172.16.0.1"}},
            ]
        }
        assert helpers.get_dst_ip(alert) == "172.16.0.1"


# ---------------------------------------------------------------------------
# get_url
# ---------------------------------------------------------------------------


class TestGetUrl:
    def test_get_url_ocsf(self, helpers, ocsf_alert):
        assert helpers.get_url(ocsf_alert) == "https://example.com/api"

    def test_get_url_empty(self, helpers):
        assert helpers.get_url({}) is None

    def test_get_url_ocsf_no_url_in_evidence(self, helpers):
        alert = {"evidences": [{"src_endpoint": {"ip": "1.2.3.4"}}]}
        assert helpers.get_url(alert) is None

    def test_get_url_multiple_evidences(self, helpers):
        alert = {
            "evidences": [
                {"src_endpoint": {"ip": "1.2.3.4"}},
                {"url": {"url_string": "https://second.example.com"}},
            ]
        }
        assert helpers.get_url(alert) == "https://second.example.com"


# ---------------------------------------------------------------------------
# get_url_path
# ---------------------------------------------------------------------------


class TestGetUrlPath:
    def test_get_url_path_ocsf(self, helpers, ocsf_alert):
        assert helpers.get_url_path(ocsf_alert) == "/api"

    def test_get_url_path_empty(self, helpers):
        assert helpers.get_url_path({}) is None

    def test_get_url_path_no_url_in_evidence(self, helpers):
        alert = {"evidences": [{"src_endpoint": {"ip": "1.2.3.4"}}]}
        assert helpers.get_url_path(alert) is None


# ---------------------------------------------------------------------------
# get_cve_ids
# ---------------------------------------------------------------------------


class TestGetCveIds:
    def test_get_cve_ids_ocsf(self, helpers, ocsf_alert):
        result = helpers.get_cve_ids(ocsf_alert)
        assert result == ["CVE-2022-41082", "CVE-2022-41040"]

    def test_get_cve_ids_empty(self, helpers):
        assert helpers.get_cve_ids({}) == []

    def test_get_cve_ids_ocsf_empty_vulns(self, helpers):
        assert helpers.get_cve_ids({"vulnerabilities": []}) == []

    def test_get_cve_ids_single_vulnerability(self, helpers):
        alert = {"vulnerabilities": [{"cve": {"uid": "CVE-2023-0001"}}]}
        assert helpers.get_cve_ids(alert) == ["CVE-2023-0001"]


# ---------------------------------------------------------------------------
# get_label
# ---------------------------------------------------------------------------


class TestGetLabel:
    def test_get_label_ocsf(self, helpers, ocsf_alert):
        assert helpers.get_label(ocsf_alert, "source_category") == "Firewall"

    def test_get_label_empty(self, helpers):
        assert helpers.get_label({}, "source_category") is None

    def test_get_label_ocsf_no_matching_label(self, helpers, ocsf_alert):
        assert helpers.get_label(ocsf_alert, "nonexistent_key") is None

    def test_get_label_ocsf_multiple_labels(self, helpers):
        alert = {
            "metadata": {
                "labels": [
                    "source_category:Firewall",
                    "environment:production",
                    "team:security",
                ]
            }
        }
        assert helpers.get_label(alert, "environment") == "production"
        assert helpers.get_label(alert, "team") == "security"

    def test_get_label_no_metadata(self, helpers):
        alert = {"severity": "High"}
        assert helpers.get_label(alert, "severity") is None

    def test_get_label_metadata_without_labels(self, helpers):
        alert = {"metadata": {"version": "1.0"}}
        assert helpers.get_label(alert, "version") is None


# ---------------------------------------------------------------------------
# get_dst_domain
# ---------------------------------------------------------------------------


class TestGetDstDomain:
    def test_get_dst_domain_ocsf(self, helpers, ocsf_alert):
        assert helpers.get_dst_domain(ocsf_alert) == "internal.corp.com"

    def test_get_dst_domain_empty(self, helpers):
        assert helpers.get_dst_domain({}) is None

    def test_get_dst_domain_no_domain_field(self, helpers):
        alert = {"evidences": [{"dst_endpoint": {"ip": "10.0.0.1"}}]}
        assert helpers.get_dst_domain(alert) is None

    def test_get_dst_domain_multiple_evidences_picks_first(self, helpers):
        alert = {
            "evidences": [
                {"src_endpoint": {"ip": "1.2.3.4"}},
                {"dst_endpoint": {"domain": "second.example.com"}},
            ]
        }
        assert helpers.get_dst_domain(alert) == "second.example.com"


# ---------------------------------------------------------------------------
# get_http_method
# ---------------------------------------------------------------------------


class TestGetHttpMethod:
    def test_get_http_method_ocsf(self, helpers, ocsf_alert):
        assert helpers.get_http_method(ocsf_alert) == "POST"

    def test_get_http_method_empty(self, helpers):
        assert helpers.get_http_method({}) is None

    def test_get_http_method_no_http_request(self, helpers):
        alert = {"evidences": [{"src_endpoint": {"ip": "1.2.3.4"}}]}
        assert helpers.get_http_method(alert) is None

    def test_get_http_method_get_request(self, helpers):
        alert = {"evidences": [{"http_request": {"http_method": "GET"}}]}
        assert helpers.get_http_method(alert) == "GET"

    def test_get_http_method_multiple_evidences_picks_first(self, helpers):
        alert = {
            "evidences": [
                {"http_request": {"http_method": "PUT"}},
                {"http_request": {"http_method": "DELETE"}},
            ]
        }
        assert helpers.get_http_method(alert) == "PUT"


# ---------------------------------------------------------------------------
# get_user_agent
# ---------------------------------------------------------------------------


class TestGetUserAgent:
    def test_get_user_agent_ocsf(self, helpers, ocsf_alert):
        assert (
            helpers.get_user_agent(ocsf_alert)
            == "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        )

    def test_get_user_agent_empty(self, helpers):
        assert helpers.get_user_agent({}) is None

    def test_get_user_agent_no_http_request(self, helpers):
        alert = {"evidences": [{"src_endpoint": {"ip": "1.2.3.4"}}]}
        assert helpers.get_user_agent(alert) is None

    def test_get_user_agent_curl(self, helpers):
        alert = {"evidences": [{"http_request": {"user_agent": "curl/7.88.1"}}]}
        assert helpers.get_user_agent(alert) == "curl/7.88.1"


# ---------------------------------------------------------------------------
# get_http_response_code
# ---------------------------------------------------------------------------


class TestGetHttpResponseCode:
    def test_get_http_response_code_ocsf(self, helpers, ocsf_alert):
        assert helpers.get_http_response_code(ocsf_alert) == 403

    def test_get_http_response_code_empty(self, helpers):
        assert helpers.get_http_response_code({}) is None

    def test_get_http_response_code_no_http_response(self, helpers):
        alert = {"evidences": [{"src_endpoint": {"ip": "1.2.3.4"}}]}
        assert helpers.get_http_response_code(alert) is None

    def test_get_http_response_code_200(self, helpers):
        alert = {"evidences": [{"http_response": {"code": 200}}]}
        assert helpers.get_http_response_code(alert) == 200

    def test_get_http_response_code_500(self, helpers):
        alert = {"evidences": [{"http_response": {"code": 500}}]}
        assert helpers.get_http_response_code(alert) == 500


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------


class TestCreateCyOcsfHelpers:
    def test_factory_returns_dict_of_callables(self):
        funcs = create_cy_ocsf_helpers()
        assert isinstance(funcs, dict)
        expected_names = [
            "get_primary_entity_type",
            "get_primary_entity_value",
            "get_primary_user",
            "get_primary_device",
            "get_primary_observable_type",
            "get_primary_observable_value",
            "get_primary_observable",
            "get_observables",
            "get_src_ip",
            "get_dst_ip",
            "get_dst_domain",
            "get_http_method",
            "get_user_agent",
            "get_http_response_code",
            "get_url",
            "get_url_path",
            "get_cve_ids",
            "get_label",
        ]
        for name in expected_names:
            assert name in funcs, f"Missing function: {name}"
            assert callable(funcs[name]), f"{name} is not callable"

    def test_factory_functions_work(self, ocsf_alert):
        funcs = create_cy_ocsf_helpers()
        assert funcs["get_primary_entity_type"](ocsf_alert) == "user"
        assert funcs["get_src_ip"](ocsf_alert) == "203.0.113.50"
        assert funcs["get_cve_ids"](ocsf_alert) == ["CVE-2022-41082", "CVE-2022-41040"]


# ---------------------------------------------------------------------------
# Documentation sync
# ---------------------------------------------------------------------------

OCSF_FIELD_REFERENCE = (
    Path(__file__).resolve().parents[3]
    / "skills"
    / "source"
    / "runbooks-manager"
    / "references"
    / "shared"
    / "ocsf-field-reference.md"
)


class TestDocsSyncWithCode:
    """Ensure ocsf-field-reference.md stays in sync with create_cy_ocsf_helpers()."""

    @staticmethod
    def _parse_documented_functions(md_path: Path) -> set[str]:
        """Extract function names from ``### func_name(...)`` headings."""
        text = md_path.read_text()
        return set(re.findall(r"^###\s+(get_\w+)\(", text, re.MULTILINE))

    def test_documented_functions_match_registered(self):
        """Every registered helper must be documented and vice-versa."""
        registered = set(create_cy_ocsf_helpers().keys())
        documented = self._parse_documented_functions(OCSF_FIELD_REFERENCE)

        missing_from_docs = registered - documented
        missing_from_code = documented - registered

        errors = []
        if missing_from_docs:
            errors.append(
                f"Registered in code but NOT documented in ocsf-field-reference.md: "
                f"{sorted(missing_from_docs)}"
            )
        if missing_from_code:
            errors.append(
                f"Documented in ocsf-field-reference.md but NOT registered in "
                f"create_cy_ocsf_helpers(): {sorted(missing_from_code)}"
            )

        assert not errors, "\n".join(errors)

    def test_detects_function_missing_from_docs(self):
        """Sync check catches a code function not documented in the markdown."""
        registered = set(create_cy_ocsf_helpers().keys()) | {"get_fake_helper"}
        documented = self._parse_documented_functions(OCSF_FIELD_REFERENCE)

        missing_from_docs = registered - documented
        assert "get_fake_helper" in missing_from_docs

    def test_detects_function_missing_from_code(self):
        """Sync check catches a documented function not registered in code."""
        registered = set(create_cy_ocsf_helpers().keys())
        documented = self._parse_documented_functions(OCSF_FIELD_REFERENCE) | {
            "get_phantom_helper"
        }

        missing_from_code = documented - registered
        assert "get_phantom_helper" in missing_from_code
