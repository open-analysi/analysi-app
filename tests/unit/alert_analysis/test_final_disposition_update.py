"""Unit tests for Final Disposition Update Step"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from analysi.alert_analysis.steps.final_disposition_update import (
    FinalDispositionUpdateStep,
)


@pytest.fixture
def disposition_step():
    """Create a FinalDispositionUpdateStep instance with mocked clients."""
    step = FinalDispositionUpdateStep()
    step.api_client = AsyncMock()
    return step


@pytest.fixture
def sample_dispositions():
    """Sample dispositions data matching the actual API response."""
    return [
        {
            "disposition_id": "7df17618-a619-4e47-9415-34b5050431e3",
            "category": "True Positive (Malicious)",
            "subcategory": "Confirmed Compromise",
            "display_name": "Confirmed Compromise",
            "color_hex": "#DC2626",
            "color_name": "red",
            "priority_score": 1,
            "requires_escalation": True,
        },
        {
            "disposition_id": "7130ed88-d3ff-44d7-8e48-5f160db25b8e",
            "category": "Undetermined",
            "subcategory": "Suspicious, Not Confirmed",
            "display_name": "Suspicious Activity",
            "color_hex": "#9333EA",
            "color_name": "purple",
            "priority_score": 4,
            "requires_escalation": True,
        },
        {
            "disposition_id": "5ed83f31-5a77-4727-9860-8a7d7463806f",
            "category": "False Positive",
            "subcategory": "Detection Logic Error",
            "display_name": "Detection Logic Error",
            "color_hex": "#EAB308",
            "color_name": "yellow",
            "priority_score": 6,
            "requires_escalation": False,
        },
    ]


@pytest.fixture
def sample_artifacts():
    """Sample workflow artifacts."""
    return [
        {
            "name": "Disposition",
            "content": "True Positive - Confirmed Compromise with 90% confidence",
        },
        {
            "name": "Alert Summary",
            "content": "Critical malware detected on endpoint requiring immediate isolation.",
        },
        {
            "name": "Detailed Analysis",
            "content": "Detailed analysis reveals advanced persistent threat indicators including command and control communication, lateral movement attempts, and data exfiltration patterns.",
        },
    ]


class TestFinalDispositionUpdateStep:
    """Test suite for FinalDispositionUpdateStep."""

    @pytest.mark.asyncio
    async def test_execute_success(
        self, disposition_step, sample_dispositions, sample_artifacts
    ):
        """Test successful execution with all artifacts present."""
        tenant_id = "test_tenant"
        alert_id = str(uuid4())
        analysis_id = str(uuid4())
        workflow_run_id = str(uuid4())

        # Mock API calls
        disposition_step.api_client.get_artifacts_by_workflow_run.return_value = (
            sample_artifacts
        )
        disposition_step.api_client.get_dispositions.return_value = sample_dispositions

        # Mock database update
        with patch.object(
            disposition_step, "_complete_analysis", new_callable=AsyncMock
        ) as mock_update:
            result = await disposition_step.execute(
                tenant_id=tenant_id,
                alert_id=alert_id,
                analysis_id=analysis_id,
                workflow_run_id=workflow_run_id,
            )

        # Verify API calls
        disposition_step.api_client.get_artifacts_by_workflow_run.assert_called_once_with(
            tenant_id, workflow_run_id
        )
        disposition_step.api_client.get_dispositions.assert_called_once_with(tenant_id)

        # Verify database update
        mock_update.assert_called_once()
        call_args = mock_update.call_args[1]
        assert call_args["analysis_id"] == analysis_id
        assert (
            call_args["disposition_id"] == "7df17618-a619-4e47-9415-34b5050431e3"
        )  # Confirmed Compromise
        assert call_args["confidence"] == 90
        assert call_args["short_summary"] == sample_artifacts[1]["content"]
        assert call_args["long_summary"] == sample_artifacts[2]["content"]

        # Verify result
        assert result["disposition_id"] == "7df17618-a619-4e47-9415-34b5050431e3"
        assert result["disposition_name"] == "Confirmed Compromise"
        assert result["confidence"] == 90
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_execute_with_missing_artifacts_falls_back_to_undetermined(
        self, disposition_step, sample_dispositions
    ):
        """Missing Disposition artifact should fall back to 'Insufficient Data'
        or any Undetermined disposition, not crash or leave blank."""
        tenant_id = "test_tenant"
        alert_id = str(uuid4())
        analysis_id = str(uuid4())
        workflow_run_id = str(uuid4())

        # Mock API calls - no artifacts returned
        disposition_step.api_client.get_artifacts_by_workflow_run.return_value = []
        disposition_step.api_client.get_dispositions.return_value = sample_dispositions

        with patch.object(
            disposition_step, "_complete_analysis", new=AsyncMock()
        ) as mock_complete:
            result = await disposition_step.execute(
                tenant_id=tenant_id,
                alert_id=alert_id,
                analysis_id=analysis_id,
                workflow_run_id=workflow_run_id,
            )

        assert result["status"] == "completed"
        assert "warning" in result
        # Should have used the Undetermined fallback disposition
        assert result["disposition_name"] == "Suspicious Activity"
        call_kwargs = mock_complete.call_args.kwargs
        assert call_kwargs["disposition_category"] == "Undetermined"

    def test_extract_confidence_with_percentage(self, disposition_step):
        """Test confidence extraction from text with percentage."""
        assert disposition_step._extract_confidence("85% confidence") == 85
        assert disposition_step._extract_confidence("confidence: 90%") == 90
        assert disposition_step._extract_confidence("50 percent confidence") == 50
        assert disposition_step._extract_confidence("Confidence: 100") == 100

    def test_extract_confidence_defaults(self, disposition_step):
        """Test confidence extraction defaults."""
        assert disposition_step._extract_confidence("") == 75
        assert disposition_step._extract_confidence(None) == 75
        assert disposition_step._extract_confidence("no confidence mentioned") == 75

    def test_extract_confidence_bounds(self, disposition_step):
        """Test confidence extraction respects bounds."""
        assert disposition_step._extract_confidence("150% confidence") == 100
        assert disposition_step._extract_confidence("-10% confidence") == 0

    @pytest.mark.asyncio
    async def test_match_disposition_exact_match(
        self, disposition_step, sample_dispositions
    ):
        """Test exact disposition matching."""
        result = await disposition_step._match_disposition(
            "Confirmed Compromise", sample_dispositions
        )
        assert result["id"] == "7df17618-a619-4e47-9415-34b5050431e3"
        assert result["name"] == "Confirmed Compromise"

    @pytest.mark.asyncio
    async def test_match_disposition_substring_match(
        self, disposition_step, sample_dispositions
    ):
        """Display name substring matching still works for legacy formats."""
        # "True Positive - Confirmed Compromise" contains display_name "Confirmed Compromise"
        result = await disposition_step._match_disposition(
            "True Positive - Confirmed Compromise", sample_dispositions
        )
        assert result["name"] == "Confirmed Compromise"

        # Direct display name match
        result = await disposition_step._match_disposition(
            "Detection Logic Error", sample_dispositions
        )
        assert result["name"] == "Detection Logic Error"

    @pytest.mark.asyncio
    async def test_vague_text_raises_instead_of_guessing(
        self, disposition_step, sample_dispositions
    ):
        """Vague text like 'true positive alert' should fail, not guess a disposition."""
        with pytest.raises(ValueError, match="No disposition match"):
            await disposition_step._match_disposition(
                "This is a true positive alert", sample_dispositions
            )

    @pytest.mark.asyncio
    async def test_match_disposition_no_match_raises(
        self, disposition_step, sample_dispositions
    ):
        """Unrecognized text should raise, not silently default."""
        with pytest.raises(ValueError, match="No disposition match"):
            await disposition_step._match_disposition(
                "Random text with no matches", sample_dispositions
            )

    @pytest.mark.asyncio
    async def test_match_disposition_no_text_raises(
        self, disposition_step, sample_dispositions
    ):
        """Missing disposition text should raise, not silently default."""
        with pytest.raises(ValueError, match="No disposition"):
            await disposition_step._match_disposition(None, sample_dispositions)

    @pytest.mark.asyncio
    async def test_extract_artifact_content(self, disposition_step, sample_artifacts):
        """Test artifact content extraction."""
        # Test existing artifact
        content = await disposition_step._extract_artifact_content(
            sample_artifacts, "Alert Summary", "test_tenant"
        )
        assert (
            content
            == "Critical malware detected on endpoint requiring immediate isolation."
        )

        # Test non-existing artifact
        content = await disposition_step._extract_artifact_content(
            sample_artifacts, "Non-Existent", "test_tenant"
        )
        assert content is None

        # Test empty artifacts list
        content = await disposition_step._extract_artifact_content(
            [], "Alert Summary", "test_tenant"
        )
        assert content is None

    @pytest.mark.asyncio
    async def test_extract_artifact_content_nested_format(self, disposition_step):
        """Test artifact content extraction with new nested JSON format."""
        # New format: artifact content is JSON with nested structure
        import json

        nested_artifacts = [
            {
                "name": "Alert Summary",
                "content": json.dumps(
                    {
                        "data_source": "AI Analysis",
                        "summary": "Critical SSH brute force attack detected from IP 185.220.101.45, risk score 14.74%, immediate blocking recommended.",
                        "summary_type": "executive",
                        "character_count": 115,
                        "enrichments_incorporated": 3,
                    }
                ),
            },
            {
                "name": "Disposition",
                "content": "True Positive - Confirmed Compromise with 90% confidence",
            },
        ]

        # Test extraction - should get just the summary text, not the whole JSON
        content = await disposition_step._extract_artifact_content(
            nested_artifacts, "Alert Summary", "test_tenant"
        )
        assert (
            content
            == "Critical SSH brute force attack detected from IP 185.220.101.45, risk score 14.74%, immediate blocking recommended."
        )

        # Test with plain text artifact (backward compatibility)
        plain_artifacts = [
            {
                "name": "Alert Summary",
                "content": "Plain text summary without nesting",
            }
        ]
        content = await disposition_step._extract_artifact_content(
            plain_artifacts, "Alert Summary", "test_tenant"
        )
        assert content == "Plain text summary without nesting"

    @pytest.mark.asyncio
    async def test_extract_artifact_detailed_analysis_nested_format(
        self, disposition_step
    ):
        """Test artifact content extraction for Detailed Analysis with nested JSON format."""
        import json

        # New format for Detailed Analysis: matches actual production structure
        # with "analysis_type", "analysis", and "context_used" fields
        nested_artifacts = [
            {
                "name": "Detailed Analysis",
                "content": json.dumps(
                    {
                        "analysis_type": "comprehensive_threat_analysis",
                        "analysis": "This alert represents a critical SSH brute force attack originating from IP 185.220.101.45, a known Tor exit node with 100% abuse confidence score. The attacker targeted prod-server-01 (10.0.1.15) on port 22 using TCP protocol. VirusTotal analysis shows 14 security vendors flagged this IP as malicious. AbuseIPDB reports 19 total abuse reports. Immediate blocking is strongly recommended to prevent potential system compromise.",
                        "context_used": {
                            "primary_ioc": "185.220.101.45",
                            "primary_ioc_type": "ip",
                            "risk_entity": "prod-server-01",
                            "risk_entity_type": "device",
                            "existing_enrichments_count": 3,
                        },
                    }
                ),
            },
        ]

        # Test extraction - should get just the analysis text, not the whole JSON
        content = await disposition_step._extract_artifact_content(
            nested_artifacts, "Detailed Analysis", "test_tenant"
        )
        assert (
            content
            == "This alert represents a critical SSH brute force attack originating from IP 185.220.101.45, a known Tor exit node with 100% abuse confidence score. The attacker targeted prod-server-01 (10.0.1.15) on port 22 using TCP protocol. VirusTotal analysis shows 14 security vendors flagged this IP as malicious. AbuseIPDB reports 19 total abuse reports. Immediate blocking is strongly recommended to prevent potential system compromise."
        )

        # Test with plain text artifact (backward compatibility)
        plain_artifacts = [
            {
                "name": "Detailed Analysis",
                "content": "Plain text detailed analysis without nesting",
            }
        ]
        content = await disposition_step._extract_artifact_content(
            plain_artifacts, "Detailed Analysis", "test_tenant"
        )
        assert content == "Plain text detailed analysis without nesting"

    @pytest.mark.asyncio
    async def test_match_disposition_with_confidence_param(
        self, disposition_step, sample_dispositions
    ):
        """Confidence should be passed through from caller."""
        result = await disposition_step._match_disposition(
            "Confirmed Compromise", sample_dispositions, confidence=85
        )
        assert result["name"] == "Confirmed Compromise"
        assert result["confidence"] == 85

    @pytest.mark.asyncio
    async def test_complete_analysis_success(self, disposition_step):
        """Test successful API-based analysis completion."""
        analysis_id = str(uuid4())
        disposition_id = str(uuid4())
        workflow_run_id = str(uuid4())

        # Mock the httpx client
        with patch(
            "analysi.alert_analysis.steps.final_disposition_update.InternalAsyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.raise_for_status = AsyncMock()
            mock_client.put.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            await disposition_step._complete_analysis(
                tenant_id="test_tenant",
                analysis_id=analysis_id,
                disposition_id=disposition_id,
                confidence=85,
                short_summary="Test summary",
                long_summary="Detailed test summary",
                workflow_run_id=workflow_run_id,
                disposition_category="Test Category",
                disposition_subcategory="Test Subcategory",
                disposition_display_name="Test Display Name",
                disposition_confidence=85,
            )

            # Verify API call was made
            mock_client.put.assert_called_once()
            call_args = mock_client.put.call_args
            assert f"/v1/test_tenant/analyses/{analysis_id}/complete" in call_args[0][0]
            assert call_args[1]["json"]["disposition_id"] == disposition_id
            assert call_args[1]["json"]["confidence"] == 85

    @pytest.mark.asyncio
    async def test_complete_analysis_failure(self, disposition_step):
        """Test API failure handling."""
        analysis_id = str(uuid4())
        disposition_id = str(uuid4())
        workflow_run_id = str(uuid4())

        # Mock the httpx client to raise an error
        with patch(
            "analysi.alert_analysis.steps.final_disposition_update.InternalAsyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client.put.side_effect = Exception("API error")
            mock_client_class.return_value.__aenter__.return_value = mock_client

            with pytest.raises(Exception, match="API error"):
                await disposition_step._complete_analysis(
                    tenant_id="test_tenant",
                    analysis_id=analysis_id,
                    disposition_id=disposition_id,
                    confidence=85,
                    short_summary="Test",
                    long_summary="Test",
                    workflow_run_id=workflow_run_id,
                )

    @pytest.mark.asyncio
    async def test_execute_forwards_workflow_id_to_complete_analysis(
        self, disposition_step, sample_dispositions, sample_artifacts
    ):
        """Test that execute() forwards workflow_id to _complete_analysis.

        Bug: workflow_id was available in the pipeline but never passed through
        to _complete_analysis, leaving alert_analysis.workflow_id NULL in the DB.
        """
        tenant_id = "test_tenant"
        alert_id = str(uuid4())
        analysis_id = str(uuid4())
        workflow_run_id = str(uuid4())
        workflow_id = str(uuid4())

        # Mock API calls
        disposition_step.api_client.get_artifacts_by_workflow_run.return_value = (
            sample_artifacts
        )
        disposition_step.api_client.get_dispositions.return_value = sample_dispositions

        with patch.object(
            disposition_step, "_complete_analysis", new_callable=AsyncMock
        ) as mock_update:
            await disposition_step.execute(
                tenant_id=tenant_id,
                alert_id=alert_id,
                analysis_id=analysis_id,
                workflow_run_id=workflow_run_id,
                workflow_id=workflow_id,
            )

        mock_update.assert_called_once()
        call_args = mock_update.call_args[1]
        assert call_args["workflow_id"] == workflow_id

    @pytest.mark.asyncio
    async def test_complete_analysis_sends_workflow_id_to_api(self, disposition_step):
        """Test that _complete_analysis sends workflow_id in the API request."""
        analysis_id = str(uuid4())
        disposition_id = str(uuid4())
        workflow_run_id = str(uuid4())
        workflow_id = str(uuid4())

        with patch(
            "analysi.alert_analysis.steps.final_disposition_update.InternalAsyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.raise_for_status = AsyncMock()
            mock_client.put.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            await disposition_step._complete_analysis(
                tenant_id="test_tenant",
                analysis_id=analysis_id,
                disposition_id=disposition_id,
                confidence=85,
                short_summary="Test summary",
                long_summary="Detailed test summary",
                workflow_run_id=workflow_run_id,
                workflow_id=workflow_id,
                disposition_category="Test Category",
                disposition_subcategory="Test Subcategory",
                disposition_display_name="Test Display Name",
                disposition_confidence=85,
            )

            call_args = mock_client.put.call_args
            assert call_args[1]["json"]["workflow_id"] == workflow_id

    @pytest.mark.asyncio
    async def test_execute_api_failure(self, disposition_step):
        """Test handling of API failures during execution."""
        tenant_id = "test_tenant"
        alert_id = str(uuid4())
        analysis_id = str(uuid4())
        workflow_run_id = str(uuid4())

        # Mock API failure
        disposition_step.api_client.get_dispositions.side_effect = Exception(
            "API Error"
        )

        with pytest.raises(Exception, match="API Error"):
            await disposition_step.execute(
                tenant_id=tenant_id,
                alert_id=alert_id,
                analysis_id=analysis_id,
                workflow_run_id=workflow_run_id,
            )


@pytest.fixture
def all_dispositions():
    """All real dispositions from the production database."""
    return [
        {
            "disposition_id": "7df17618-a619-4e47-9415-34b5050431e3",
            "category": "True Positive (Malicious)",
            "subcategory": "Confirmed Compromise",
            "display_name": "Confirmed Compromise",
        },
        {
            "disposition_id": "20e4c83f-c43e-4c4f-989b-36a3e1d78794",
            "category": "True Positive (Malicious)",
            "subcategory": "Confirmed Malicious Attempt (Blocked/Prevented, No Impact)",
            "display_name": "Malicious Attempt Blocked",
        },
        {
            "disposition_id": "a2185683-cde6-48ed-8ede-d38a9848edf6",
            "category": "True Positive (Policy Violation)",
            "subcategory": "Unauthorized Access / Privilege Misuse",
            "display_name": "Unauthorized Access",
        },
        {
            "disposition_id": "02548750-1243-46a2-91da-a8c9f6f98fbe",
            "category": "True Positive (Policy Violation)",
            "subcategory": "Acceptable Use Violation (non-security but against policy)",
            "display_name": "Acceptable Use Violation",
        },
        {
            "disposition_id": "5ed83f31-5a77-4727-9860-8a7d7463806f",
            "category": "False Positive",
            "subcategory": "Detection Logic Error",
            "display_name": "Detection Logic Error",
        },
        {
            "disposition_id": "6efbd1e6-56d7-4c1e-9546-f498aa08a591",
            "category": "False Positive",
            "subcategory": "Rule Misconfiguration / Sensitivity Issue",
            "display_name": "Rule Misconfiguration",
        },
        {
            "disposition_id": "6e04b1bf-3d7a-4825-b740-df26cdb21a25",
            "category": "False Positive",
            "subcategory": "Vendor Signature Bug",
            "display_name": "Vendor Signature Bug",
        },
        {
            "disposition_id": "e005e017-fba3-45d6-89f7-d605161fb031",
            "category": "Benign Explained",
            "subcategory": "Known Business Process",
            "display_name": "Business Process",
        },
        {
            "disposition_id": "ee1a2472-b9ba-4355-88ae-2962f159b1a5",
            "category": "Benign Explained",
            "subcategory": "Environmental Noise (e.g., server patching or restart)",
            "display_name": "Environmental Noise",
        },
        {
            "disposition_id": "8dba06ee-e1a9-4550-b2da-fb96634a9f0c",
            "category": "Benign Explained",
            "subcategory": "IT Maintenance / Patch / Scanning",
            "display_name": "IT Maintenance",
        },
        {
            "disposition_id": "f210309d-6b2d-4f6b-9d2a-ceeb7d346409",
            "category": "Security Testing / Expected Activity",
            "subcategory": "Red Team / Pentest",
            "display_name": "Red Team Activity",
        },
        {
            "disposition_id": "d913b956-9a65-4098-bf33-046703db39c4",
            "category": "Security Testing / Expected Activity",
            "subcategory": "Compliance / Audit",
            "display_name": "Compliance Testing",
        },
        {
            "disposition_id": "1b432562-a5c4-4088-83b2-b77a4de982dc",
            "category": "Security Testing / Expected Activity",
            "subcategory": "Training / Tabletop",
            "display_name": "Training Exercise",
        },
        {
            "disposition_id": "7130ed88-d3ff-44d7-8e48-5f160db25b8e",
            "category": "Undetermined",
            "subcategory": "Suspicious, Not Confirmed",
            "display_name": "Suspicious Activity",
        },
        {
            "disposition_id": "38582dbd-f8c6-48ab-87e9-9bba241a0b5a",
            "category": "Undetermined",
            "subcategory": "Insufficient Data / Logs Missing",
            "display_name": "Insufficient Data",
        },
        {
            "disposition_id": "48072b83-74a4-4480-af11-a1aa13c5ea29",
            "category": "Undetermined",
            "subcategory": "Escalated for Review",
            "display_name": "Escalated for Review",
        },
        {
            "disposition_id": "d98cb36a-175e-42e5-a69d-45c3785569dc",
            "category": "Analysis Stopped by User",
            "subcategory": "Invalid Alert",
            "display_name": "Invalid Alert",
        },
        {
            "disposition_id": "cad22e34-15d0-4366-ad34-66dd33e8ea9a",
            "category": "Analysis Stopped by User",
            "subcategory": "Known Issue / Duplicate",
            "display_name": "Known Issue/Duplicate",
        },
    ]


class TestStructuredDispositionParsing:
    """Fix 1: Parse the CATEGORY / DISPLAY_NAME format the LLM outputs.

    Real LLM output follows a clear convention:
        "TRUE POSITIVE (Malicious) / Malicious Attempt Blocked"
        "False Positive / Detection Logic Error"
        "Undetermined / Suspicious Activity"

    Step 4 should parse this structure rather than substring-match.
    """

    @pytest.mark.asyncio
    async def test_real_llm_output_format(self, disposition_step, all_dispositions):
        """Match the exact format seen in production artifacts."""
        result = await disposition_step._match_disposition(
            "TRUE POSITIVE (Malicious) / Malicious Attempt Blocked",
            all_dispositions,
        )
        assert result["name"] == "Malicious Attempt Blocked"
        assert result["id"] == "20e4c83f-c43e-4c4f-989b-36a3e1d78794"

    @pytest.mark.asyncio
    async def test_confirmed_compromise(self, disposition_step, all_dispositions):
        """Parse structured format for confirmed compromise."""
        result = await disposition_step._match_disposition(
            "True Positive (Malicious) / Confirmed Compromise",
            all_dispositions,
        )
        assert result["name"] == "Confirmed Compromise"

    @pytest.mark.asyncio
    async def test_false_positive_structured(self, disposition_step, all_dispositions):
        """Parse structured format for false positive dispositions."""
        result = await disposition_step._match_disposition(
            "False Positive / Detection Logic Error",
            all_dispositions,
        )
        assert result["name"] == "Detection Logic Error"

    @pytest.mark.asyncio
    async def test_false_positive_rule_misconfig(
        self, disposition_step, all_dispositions
    ):
        """Parse structured format for rule misconfiguration."""
        result = await disposition_step._match_disposition(
            "False Positive / Rule Misconfiguration",
            all_dispositions,
        )
        assert result["name"] == "Rule Misconfiguration"

    @pytest.mark.asyncio
    async def test_benign_explained(self, disposition_step, all_dispositions):
        """Parse structured format for benign explained dispositions."""
        result = await disposition_step._match_disposition(
            "Benign Explained / Business Process",
            all_dispositions,
        )
        assert result["name"] == "Business Process"

    @pytest.mark.asyncio
    async def test_undetermined_suspicious(self, disposition_step, all_dispositions):
        """Parse structured format for undetermined."""
        result = await disposition_step._match_disposition(
            "Undetermined / Suspicious Activity",
            all_dispositions,
        )
        assert result["name"] == "Suspicious Activity"

    @pytest.mark.asyncio
    async def test_policy_violation(self, disposition_step, all_dispositions):
        """Parse structured format for policy violation dispositions."""
        result = await disposition_step._match_disposition(
            "True Positive (Policy Violation) / Unauthorized Access",
            all_dispositions,
        )
        assert result["name"] == "Unauthorized Access"

    @pytest.mark.asyncio
    async def test_security_testing(self, disposition_step, all_dispositions):
        """Parse structured format for security testing dispositions."""
        result = await disposition_step._match_disposition(
            "Security Testing / Expected Activity / Red Team Activity",
            all_dispositions,
        )
        assert result["name"] == "Red Team Activity"

    @pytest.mark.asyncio
    async def test_case_insensitive_format(self, disposition_step, all_dispositions):
        """Structured parsing should be case-insensitive on display name."""
        result = await disposition_step._match_disposition(
            "true positive (malicious) / malicious attempt blocked",
            all_dispositions,
        )
        assert result["name"] == "Malicious Attempt Blocked"

    @pytest.mark.asyncio
    async def test_whitespace_tolerance(self, disposition_step, all_dispositions):
        """Handle extra whitespace around the separator."""
        result = await disposition_step._match_disposition(
            "True Positive (Malicious)  /  Confirmed Compromise",
            all_dispositions,
        )
        assert result["name"] == "Confirmed Compromise"


class TestConfidenceFromDetailedAnalysis:
    """Fix 2: Extract confidence from Detailed Analysis artifact.

    In production, confidence appears in the Detailed Analysis
    (e.g., "High (80% confidence)"), NOT in the Disposition artifact.
    Step 4's execute() should look there when Disposition has no confidence.
    """

    @pytest.mark.asyncio
    async def test_confidence_extracted_from_detailed_analysis(self, disposition_step):
        """Real-world case: Disposition has no confidence, Detailed Analysis does."""
        artifacts = [
            {
                "name": "Disposition",
                "content": "TRUE POSITIVE (Malicious) / Malicious Attempt Blocked",
            },
            {
                "name": "Alert Summary",
                "content": "SQL injection attempt detected and blocked.",
            },
            {
                "name": "Detailed Analysis",
                "content": (
                    "### Security Analysis Report\n"
                    "The attack was blocked at the application layer.\n"
                    "**Confidence Level**: High (80% confidence) in the assessment."
                ),
            },
        ]

        all_disps = [
            {
                "disposition_id": "20e4c83f-c43e-4c4f-989b-36a3e1d78794",
                "category": "True Positive (Malicious)",
                "subcategory": "Confirmed Malicious Attempt (Blocked/Prevented, No Impact)",
                "display_name": "Malicious Attempt Blocked",
            },
        ]

        disposition_step.api_client.get_artifacts_by_workflow_run.return_value = (
            artifacts
        )
        disposition_step.api_client.get_dispositions.return_value = all_disps

        with patch.object(
            disposition_step, "_complete_analysis", new_callable=AsyncMock
        ) as mock_complete:
            result = await disposition_step.execute(
                tenant_id="test_tenant",
                alert_id=str(uuid4()),
                analysis_id=str(uuid4()),
                workflow_run_id=str(uuid4()),
            )

        assert result["confidence"] == 80
        call_args = mock_complete.call_args[1]
        assert call_args["confidence"] == 80

    @pytest.mark.asyncio
    async def test_disposition_confidence_takes_priority(self, disposition_step):
        """If Disposition text has explicit confidence, use that over Detailed Analysis."""
        artifacts = [
            {
                "name": "Disposition",
                "content": "True Positive - Confirmed Compromise with 90% confidence",
            },
            {
                "name": "Alert Summary",
                "content": "Attack detected.",
            },
            {
                "name": "Detailed Analysis",
                "content": "**Confidence Level**: High (70% confidence)",
            },
        ]

        all_disps = [
            {
                "disposition_id": "7df17618-a619-4e47-9415-34b5050431e3",
                "category": "True Positive (Malicious)",
                "subcategory": "Confirmed Compromise",
                "display_name": "Confirmed Compromise",
            },
        ]

        disposition_step.api_client.get_artifacts_by_workflow_run.return_value = (
            artifacts
        )
        disposition_step.api_client.get_dispositions.return_value = all_disps

        with patch.object(
            disposition_step, "_complete_analysis", new_callable=AsyncMock
        ):
            result = await disposition_step.execute(
                tenant_id="test_tenant",
                alert_id=str(uuid4()),
                analysis_id=str(uuid4()),
                workflow_run_id=str(uuid4()),
            )

        assert result["confidence"] == 90

    @pytest.mark.asyncio
    async def test_no_confidence_anywhere_defaults_to_75(self, disposition_step):
        """If neither artifact has a confidence, fall back to 75% default."""
        artifacts = [
            {
                "name": "Disposition",
                "content": "TRUE POSITIVE (Malicious) / Malicious Attempt Blocked",
            },
            {"name": "Alert Summary", "content": "Attack detected."},
            {
                "name": "Detailed Analysis",
                "content": "The attack was blocked. No further action needed.",
            },
        ]

        all_disps = [
            {
                "disposition_id": "20e4c83f-c43e-4c4f-989b-36a3e1d78794",
                "category": "True Positive (Malicious)",
                "subcategory": "Confirmed Malicious Attempt (Blocked/Prevented, No Impact)",
                "display_name": "Malicious Attempt Blocked",
            },
        ]

        disposition_step.api_client.get_artifacts_by_workflow_run.return_value = (
            artifacts
        )
        disposition_step.api_client.get_dispositions.return_value = all_disps

        with patch.object(
            disposition_step, "_complete_analysis", new_callable=AsyncMock
        ):
            result = await disposition_step.execute(
                tenant_id="test_tenant",
                alert_id=str(uuid4()),
                analysis_id=str(uuid4()),
                workflow_run_id=str(uuid4()),
            )

        assert result["confidence"] == 75


class TestDispositionMatchFailure:
    """Fix 3: Fail clearly when no disposition matches.

    Silent defaulting to 'Suspicious Activity' hides real problems.
    If the analysis produced a clear disposition and Step 4 can't map it
    to a DB record, that's a bug that should be visible.
    """

    @pytest.mark.asyncio
    async def test_unrecognized_disposition_raises(
        self, disposition_step, all_dispositions
    ):
        """Unrecognized disposition text should raise, not silently default."""
        with pytest.raises(ValueError, match="No disposition match"):
            await disposition_step._match_disposition(
                "Some Completely Unknown Disposition Text",
                all_dispositions,
            )

    @pytest.mark.asyncio
    async def test_no_disposition_text_raises(self, disposition_step, all_dispositions):
        """Missing disposition text (None) should raise, not silently default."""
        with pytest.raises(ValueError, match="No disposition"):
            await disposition_step._match_disposition(None, all_dispositions)

    @pytest.mark.asyncio
    async def test_empty_disposition_text_raises(
        self, disposition_step, all_dispositions
    ):
        """Empty string disposition text should raise, not silently default."""
        with pytest.raises(ValueError, match="No disposition"):
            await disposition_step._match_disposition("", all_dispositions)
