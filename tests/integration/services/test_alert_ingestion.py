"""
Integration tests for alert ingestion from Naxos connectors.

Tests the complete flow:
1. Connector pulls raw alerts from source
2. AlertIngestionService normalizes and persists to database
3. Alert analysis is triggered
"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select

from analysi.integrations.framework.alert_ingest import AlertIngestionService
from analysi.models.alert import Alert
from analysi.repositories.alert_repository import AlertRepository


@pytest.mark.integration
class TestAlertIngestion:
    """Test alert ingestion from connectors."""

    @pytest.mark.asyncio
    async def test_splunk_alert_ingestion(self, integration_test_session):
        """Test ingesting Splunk notable events into alerts table."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Sample Splunk notable event (from real Splunk output)
        raw_splunk_alerts = [
            {
                "_time": "2025-10-04T20:14:45.881+00:00",
                "rule_name": "Possible SQL Injection Payload Detected",
                "rule_title": "Possible SQL Injection Payload Detected",
                "rule_description": "Alert triggered because the requested URL contained a potential SQL injection payload.",
                "severity": "high",
                "urgency": "medium",
                "priority": "unknown",
                "status": "1",
                "status_label": "New",
                "owner": "unassigned",
                "dest": "172.16.17.18",
                "src": "167.99.169.17",
                "risk_score": "80",
                "event_id": "B1C3D4E5-F6A4-8B9C-0D1E-F2A3B4C5D6E7@@notable@@a1b2c3d4e5f67890abcdrf1234567890",
            },
            {
                "_time": "2025-10-04T20:14:45.805+00:00",
                "rule_name": "PowerShell Found in Requested URL - Possible CVE-2022-41082 Exploitation",
                "rule_title": "PowerShell Found in Requested URL",
                "severity": "high",
                "dest": "172.16.20.8",
                "src": "58.237.200.6",
                "risk_score": "80",
            },
        ]

        # Create ingestion service
        ingest_service = AlertIngestionService(integration_test_session)

        # Ingest alerts
        result = await ingest_service.ingest_alerts(
            tenant_id=tenant_id,
            integration_type="splunk",
            raw_alerts=raw_splunk_alerts,
        )

        # Verify ingestion results
        assert result["created"] == 2
        assert result["duplicates"] == 0
        assert result["errors"] == 0

        # Verify alerts were persisted to database
        alert_repo = AlertRepository(integration_test_session)
        alerts, total = await alert_repo.find_by_filters(tenant_id, limit=10)

        assert len(alerts) == 2

        # Verify first alert details
        alert1 = alerts[0]
        assert alert1.title == "Possible SQL Injection Payload Detected"
        assert alert1.severity == "high"
        assert alert1.source_vendor == "Splunk"
        assert alert1.source_product == "Enterprise Security"

        # OCSF: rule_name must be persisted from finding_info.analytic.name
        assert alert1.rule_name == "Possible SQL Injection Payload Detected"

        # OCSF: finding_info must contain both title and analytic (rule name)
        assert alert1.finding_info is not None
        assert alert1.finding_info.get("title") is not None
        assert alert1.finding_info.get("analytic", {}).get("name") == alert1.rule_name

        # OCSF: device should contain the primary risk entity (dest IP)
        assert alert1.device is not None
        assert alert1.device.get("ip") == "172.16.17.18"

        # Verify raw data is preserved
        assert alert1.raw_data is not None

        # Verify second alert rule_name + finding_info.analytic consistency
        alert2 = alerts[1]
        assert alert2.rule_name is not None
        assert alert2.finding_info is not None
        assert alert2.finding_info.get("analytic", {}).get("name") == alert2.rule_name

    @pytest.mark.asyncio
    async def test_duplicate_alert_handling(self, integration_test_session):
        """Test that duplicate alerts are detected and not created twice."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        raw_alert = {
            "_time": "2025-10-04T20:14:45.881+00:00",
            "rule_name": "Test Alert",
            "severity": "medium",
            "dest": "10.0.0.1",
            "src": "10.0.0.2",
        }

        ingest_service = AlertIngestionService(integration_test_session)

        # Ingest first time
        result1 = await ingest_service.ingest_alerts(
            tenant_id=tenant_id,
            integration_type="splunk",
            raw_alerts=[raw_alert],
        )

        assert result1["created"] == 1
        assert result1["duplicates"] == 0

        # Ingest same alert again
        result2 = await ingest_service.ingest_alerts(
            tenant_id=tenant_id,
            integration_type="splunk",
            raw_alerts=[raw_alert],
        )

        # Should be detected as duplicate
        assert result2["created"] == 0
        assert result2["duplicates"] == 1

        # Verify only one alert in database
        alert_repo = AlertRepository(integration_test_session)
        alerts, total = await alert_repo.find_by_filters(tenant_id, limit=10)
        assert len(alerts) == 1

    @pytest.mark.asyncio
    async def test_normalizer_auto_detection(self, integration_test_session):
        """Test that normalizer is auto-detected for integration type."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        raw_alert = {
            "_time": "2025-10-04T20:14:45.881+00:00",
            "rule_name": "Test Alert",
            "severity": "low",
            "dest": "10.0.0.1",
        }

        ingest_service = AlertIngestionService(integration_test_session)

        # Should auto-detect SplunkNotableNormalizer for splunk type
        result = await ingest_service.ingest_alerts(
            tenant_id=tenant_id,
            integration_type="splunk",
            raw_alerts=[raw_alert],
        )

        assert result["created"] == 1

        # Verify alert was normalized correctly
        alert_repo = AlertRepository(integration_test_session)
        alerts, total = await alert_repo.find_by_filters(tenant_id, limit=1)

        assert len(alerts) == 1
        assert alerts[0].source_vendor == "Splunk"
        assert alerts[0].source_product == "Enterprise Security"

    @pytest.mark.asyncio
    async def test_unknown_integration_type(self, integration_test_session):
        """Test that unknown integration types fail gracefully."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        raw_alert = {"some": "data"}

        ingest_service = AlertIngestionService(integration_test_session)

        # Try to ingest with unknown integration type
        result = await ingest_service.ingest_alerts(
            tenant_id=tenant_id,
            integration_type="unknown_integration",
            raw_alerts=[raw_alert],
        )

        # Should fail to find normalizer
        assert result["created"] == 0
        assert result["errors"] == 1

    @pytest.mark.asyncio
    async def test_malformed_alert_handling(self, integration_test_session):
        """Test that malformed alerts are logged as errors."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Mix of valid and invalid alerts
        raw_alerts = [
            {
                "_time": "2025-10-04T20:14:45.881+00:00",
                "rule_name": "Valid Alert",
                "severity": "high",
                "dest": "10.0.0.1",
            },
            {
                # Missing required fields - should fail normalization
                "invalid": "alert",
            },
            {
                "_time": "2025-10-04T20:14:46.000+00:00",
                "rule_name": "Another Valid Alert",
                "severity": "low",
                "dest": "10.0.0.2",
            },
        ]

        ingest_service = AlertIngestionService(integration_test_session)

        result = await ingest_service.ingest_alerts(
            tenant_id=tenant_id,
            integration_type="splunk",
            raw_alerts=raw_alerts,
        )

        # Should create 2 valid alerts and log 1 error
        assert result["created"] == 2
        assert result["errors"] == 1

        # Verify only valid alerts were persisted
        alert_repo = AlertRepository(integration_test_session)
        alerts, total = await alert_repo.find_by_filters(tenant_id, limit=10)
        assert len(alerts) == 2

    @pytest.mark.asyncio
    async def test_empty_alerts_list(self, integration_test_session):
        """Test handling of empty alerts list."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        ingest_service = AlertIngestionService(integration_test_session)

        result = await ingest_service.ingest_alerts(
            tenant_id=tenant_id,
            integration_type="splunk",
            raw_alerts=[],
        )

        assert result["created"] == 0
        assert result["duplicates"] == 0
        assert result["errors"] == 0

    @pytest.mark.asyncio
    async def test_deduplication_uses_event_id(self, integration_test_session):
        """Test that deduplication uses source_event_id (Splunk event_id) when available."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Create two alerts with same content but different event_ids
        alert1 = {
            "_time": "2025-10-04T20:14:45.881+00:00",
            "rule_name": "Test Alert",
            "severity": "high",
            "dest": "10.0.0.1",
            "event_id": "event-123",  # Unique event ID
        }

        alert2 = {
            "_time": "2025-10-04T20:14:45.881+00:00",
            "rule_name": "Test Alert",  # Same title
            "severity": "high",  # Same severity
            "dest": "10.0.0.1",  # Same dest
            "event_id": "event-456",  # Different event ID
        }

        ingest_service = AlertIngestionService(integration_test_session)

        # Ingest first alert
        result1 = await ingest_service.ingest_alerts(
            tenant_id=tenant_id,
            integration_type="splunk",
            raw_alerts=[alert1],
        )

        assert result1["created"] == 1
        assert result1["duplicates"] == 0

        # Ingest second alert with different event_id
        result2 = await ingest_service.ingest_alerts(
            tenant_id=tenant_id,
            integration_type="splunk",
            raw_alerts=[alert2],
        )

        # Should create a new alert because event_id is different
        assert result2["created"] == 1
        assert result2["duplicates"] == 0

        # Verify two separate alerts exist
        alert_repo = AlertRepository(integration_test_session)
        alerts, total = await alert_repo.find_by_filters(tenant_id, limit=10)
        assert len(alerts) == 2
        assert alerts[0].source_event_id != alerts[1].source_event_id

        # Now ingest the first alert again with same event_id
        result3 = await ingest_service.ingest_alerts(
            tenant_id=tenant_id,
            integration_type="splunk",
            raw_alerts=[alert1],
        )

        # Should be detected as duplicate because event_id matches
        assert result3["created"] == 0
        assert result3["duplicates"] == 1

    @pytest.mark.asyncio
    async def test_severity_normalization(self, integration_test_session):
        """Test that severity values are normalized correctly."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Test various severity formats
        test_cases = [
            ("critical", "critical"),
            ("CRITICAL", "critical"),
            ("crit", "critical"),
            ("high", "high"),
            ("HIGH", "high"),
            ("medium", "medium"),
            ("med", "medium"),
            ("low", "low"),
            ("info", "info"),
            ("informational", "info"),
            ("unknown", "info"),  # Maps to info
        ]

        ingest_service = AlertIngestionService(integration_test_session)

        for input_severity, expected_severity in test_cases:
            alert_id = uuid4().hex[:8]
            raw_alert = {
                "_time": "2025-10-04T20:14:45.881+00:00",
                "rule_name": f"Test Alert {alert_id}",
                "severity": input_severity,
                "dest": f"10.0.0.{alert_id[:2]}",
            }

            result = await ingest_service.ingest_alerts(
                tenant_id=tenant_id,
                integration_type="splunk",
                raw_alerts=[raw_alert],
            )

            assert result["created"] == 1

            # Verify normalized severity
            stmt = select(Alert).where(
                Alert.tenant_id == tenant_id, Alert.title == f"Test Alert {alert_id}"
            )
            result_obj = await integration_test_session.execute(stmt)
            alert = result_obj.scalar_one()

            assert alert.severity == expected_severity, (
                f"Expected {expected_severity} for input {input_severity}, got {alert.severity}"
            )

    @pytest.mark.asyncio
    async def test_observable_confidence_is_integer(self, integration_test_session):
        """Test that OCSF observable reputation scores are integers.

        Regression test: Previously IOC confidence was stored as strings.
        OCSF observables use reputation.base_score (0-100 integer scale).
        """
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Alert with IP and URL that should generate observables
        raw_alert = {
            "_time": "2025-10-04T20:14:45.881+00:00",
            "rule_name": "Test IOC Confidence",
            "severity": "high",
            "src": "185.220.101.45",  # External IP -> should become observable
            "dest": "172.16.17.18",  # Internal IP -> should become device
            "url": "http://evil.com/malware.exe",  # URL -> should become observable
            "user_agent": "Mozilla/5.0 zgrab/0.x",  # Suspicious UA -> should become observable
        }

        ingest_service = AlertIngestionService(integration_test_session)
        result = await ingest_service.ingest_alerts(
            tenant_id=tenant_id,
            integration_type="splunk",
            raw_alerts=[raw_alert],
        )

        assert result["created"] == 1
        assert result["errors"] == 0

        # Verify OCSF observables have integer reputation scores
        alert_repo = AlertRepository(integration_test_session)
        alerts, total = await alert_repo.find_by_filters(tenant_id, limit=1)

        assert len(alerts) == 1
        alert = alerts[0]

        # Observables should exist (OCSF replacement for IOCs)
        assert alert.observables is not None
        assert len(alert.observables) > 0

        for obs in alert.observables:
            rep = obs.get("reputation")
            if rep and rep.get("base_score") is not None:
                assert isinstance(rep["base_score"], int), (
                    f"Observable reputation base_score should be int, "
                    f"got {type(rep['base_score'])}: {rep['base_score']}"
                )
                assert 0 <= rep["base_score"] <= 100, (
                    f"Observable reputation base_score should be 0-100, got {rep['base_score']}"
                )

    @pytest.mark.asyncio
    async def test_network_info_in_evidences(self, integration_test_session):
        """Test that network info is captured in OCSF evidences from Splunk notable fields."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        raw_alert = {
            "_time": "2025-10-04T20:14:45.881+00:00",
            "rule_name": "Network Alert Test",
            "severity": "high",
            "src": "10.0.0.1",
            "src_port": "54321",
            "dest": "192.168.1.100",
            "dest_port": "443",
            "protocol": "TCP",
            "bytes_in": "1024",
            "bytes_out": "2048",
        }

        ingest_service = AlertIngestionService(integration_test_session)
        result = await ingest_service.ingest_alerts(
            tenant_id=tenant_id,
            integration_type="splunk",
            raw_alerts=[raw_alert],
        )

        assert result["created"] == 1

        alert_repo = AlertRepository(integration_test_session)
        alerts, _ = await alert_repo.find_by_filters(tenant_id, limit=1)

        alert = alerts[0]
        # OCSF: network info lives in evidences as src_endpoint / dst_endpoint
        assert alert.evidences is not None
        assert len(alert.evidences) > 0

        evidence = alert.evidences[0]
        assert evidence.get("src_endpoint", {}).get("ip") == "10.0.0.1"
        assert evidence.get("dst_endpoint", {}).get("ip") == "192.168.1.100"
        assert evidence.get("dst_endpoint", {}).get("port") == "443"

    @pytest.mark.asyncio
    async def test_web_info_in_evidences(self, integration_test_session):
        """Test that web/HTTP info is captured in OCSF evidences."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        raw_alert = {
            "_time": "2025-10-04T20:14:45.881+00:00",
            "rule_name": "Web Attack Test",
            "severity": "high",
            "src": "185.220.101.45",
            "dest": "172.16.17.18",
            "url": "https://example.com/api/users?id=1",
            "http_method": "GET",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "http_referrer": "https://google.com",
        }

        ingest_service = AlertIngestionService(integration_test_session)
        result = await ingest_service.ingest_alerts(
            tenant_id=tenant_id,
            integration_type="splunk",
            raw_alerts=[raw_alert],
        )

        assert result["created"] == 1

        alert_repo = AlertRepository(integration_test_session)
        alerts, _ = await alert_repo.find_by_filters(tenant_id, limit=1)

        alert = alerts[0]
        # OCSF: web info lives in evidences as url + http_request
        assert alert.evidences is not None
        assert len(alert.evidences) > 0

        evidence = alert.evidences[0]
        url_obj = evidence.get("url", {})
        assert "example.com" in (url_obj.get("url_string") or "")
        assert evidence.get("http_request", {}).get("http_method") == "GET"

    @pytest.mark.asyncio
    async def test_process_info_in_evidences(self, integration_test_session):
        """Test that process info is captured in OCSF evidences."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        raw_alert = {
            "_time": "2025-10-04T20:14:45.881+00:00",
            "rule_name": "Process Alert Test",
            "severity": "high",
            "dest": "172.16.17.18",
            "process_name": "powershell.exe",
            "process_path": "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
            "process_id": "1234",
            "parent_process_name": "cmd.exe",
            "command_line": "powershell.exe -enc SGVsbG8gV29ybGQ=",
        }

        ingest_service = AlertIngestionService(integration_test_session)
        result = await ingest_service.ingest_alerts(
            tenant_id=tenant_id,
            integration_type="splunk",
            raw_alerts=[raw_alert],
        )

        assert result["created"] == 1

        alert_repo = AlertRepository(integration_test_session)
        alerts, _ = await alert_repo.find_by_filters(tenant_id, limit=1)

        alert = alerts[0]
        # OCSF: process info lives in evidences[].process
        assert alert.evidences is not None
        assert len(alert.evidences) > 0

        process = alert.evidences[0].get("process", {})
        assert process.get("name") == "powershell.exe"
        assert "powershell" in (process.get("cmd_line") or "").lower()

    @pytest.mark.asyncio
    async def test_vulnerabilities_populated(self, integration_test_session):
        """Test that OCSF vulnerabilities are populated when CVE references exist."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        raw_alert = {
            "_time": "2025-10-04T20:14:45.881+00:00",
            "rule_name": "CVE-2022-41082 Exploitation Attempt",
            "rule_description": "Possible exploitation of CVE-2022-41082 detected",
            "severity": "critical",
            "dest": "172.16.17.18",
            "cve_id": "CVE-2022-41082",
        }

        ingest_service = AlertIngestionService(integration_test_session)
        result = await ingest_service.ingest_alerts(
            tenant_id=tenant_id,
            integration_type="splunk",
            raw_alerts=[raw_alert],
        )

        assert result["created"] == 1

        alert_repo = AlertRepository(integration_test_session)
        alerts, _ = await alert_repo.find_by_filters(tenant_id, limit=1)

        alert = alerts[0]
        # OCSF: CVE info lives in vulnerabilities[].cve.uid
        assert alert.vulnerabilities is not None
        assert len(alert.vulnerabilities) > 0

        cve_uids = [v.get("cve", {}).get("uid") for v in alert.vulnerabilities]
        assert "CVE-2022-41082" in cve_uids

    @pytest.mark.asyncio
    async def test_info_columns_accept_none(self, integration_test_session):
        """Test that new info columns (file_info, email_info, cloud_info) accept None values."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Minimal alert without file/email/cloud context
        raw_alert = {
            "_time": "2025-10-04T20:14:45.881+00:00",
            "rule_name": "Minimal Alert",
            "severity": "low",
            "dest": "10.0.0.1",
        }

        ingest_service = AlertIngestionService(integration_test_session)
        result = await ingest_service.ingest_alerts(
            tenant_id=tenant_id,
            integration_type="splunk",
            raw_alerts=[raw_alert],
        )

        assert result["created"] == 1
        assert result["errors"] == 0

        alert_repo = AlertRepository(integration_test_session)
        alerts, _ = await alert_repo.find_by_filters(tenant_id, limit=1)

        alert = alerts[0]
        # These columns should exist but be None for this alert type
        # The key thing is no error was raised during ingestion
        assert alert.title == "Minimal Alert"

    @pytest.mark.asyncio
    async def test_trigger_analysis_called_with_correct_alert_id(
        self, integration_test_session
    ):
        """Regression: _trigger_analysis must use alert_id, not .id.

        AlertService.create_alert returns AlertResponse which has alert_id
        (not id). Using .id causes AttributeError and silently skips analysis.
        """
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        raw_alert = {
            "_time": "2025-10-04T20:14:45.881+00:00",
            "rule_name": "Trigger Test Alert",
            "severity": "high",
            "dest": "10.0.0.1",
        }

        ingest_service = AlertIngestionService(integration_test_session)

        with patch.object(
            ingest_service, "_trigger_analysis", new_callable=AsyncMock
        ) as mock_trigger:
            result = await ingest_service.ingest_alerts(
                tenant_id=tenant_id,
                integration_type="splunk",
                raw_alerts=[raw_alert],
            )

        assert result["created"] == 1
        assert result["errors"] == 0

        # _trigger_analysis must have been called exactly once
        mock_trigger.assert_called_once()
        call_args = mock_trigger.call_args
        called_tenant = call_args[0][0]
        called_alert_id = call_args[0][1]

        assert called_tenant == tenant_id
        # alert_id must be a valid UUID, not None or AttributeError
        assert called_alert_id is not None, (
            "_trigger_analysis called with None alert_id — "
            "likely using .id instead of .alert_id on AlertResponse"
        )
