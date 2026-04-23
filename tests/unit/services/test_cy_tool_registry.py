"""Unit tests for cy_tool_registry service."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from analysi.services.cy_tool_registry import load_tool_registry_async


class TestCyToolRegistry:
    """Unit tests for Cy tool registry loading."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_load_tool_registry_includes_required_field(self, mock_session):
        """
        Test that load_tool_registry_async includes 'required' field from input_schema.

        This is a regression test for a bug where optional parameters were treated as
        required because the 'required' array was not extracted from input_schema.

        Example: ad_ldap::run_query has 'search_base' as optional parameter, but it was
        being validated as required, causing task creation to fail.
        """
        # Create mock tool with optional parameter (search_base is NOT in required array)
        mock_tool = MagicMock()
        mock_tool.input_schema = {
            "type": "object",
            "properties": {
                "filter": {"type": "string", "description": "LDAP filter"},
                "attributes": {"type": "string", "description": "Attributes to return"},
                "search_base": {
                    "type": "string",
                    "description": "Search base (optional)",
                },
            },
            "required": ["filter", "attributes"],  # search_base is OPTIONAL!
        }
        mock_tool.output_schema = {
            "type": "object",
            "properties": {"results": {"type": "array"}},
        }

        # Mock component with proper FQN
        mock_component = MagicMock()
        mock_component.name = "ad_ldap::run_query"
        mock_tool.component = mock_component

        # Mock database query
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_tool]
        mock_session.execute.return_value = mock_result
        mock_session.refresh = AsyncMock()

        # Mock framework manifest loading to avoid file I/O overhead
        from unittest.mock import patch

        with patch(
            "analysi.services.integration_registry_service.IntegrationRegistryService"
        ) as mock_registry:
            mock_framework = MagicMock()
            mock_framework.list_integrations.return_value = []  # No framework tools for this test
            mock_registry.return_value.framework = mock_framework

            # Load tool registry
            tool_registry = await load_tool_registry_async(mock_session, "default")

        # Verify FQN is correct
        assert "app::ad_ldap::run_query" in tool_registry

        tool_schema = tool_registry["app::ad_ldap::run_query"]

        # Verify parameters are extracted
        assert "parameters" in tool_schema
        assert "filter" in tool_schema["parameters"]
        assert "attributes" in tool_schema["parameters"]
        assert "search_base" in tool_schema["parameters"]

        # BUG FIX VERIFICATION: Verify 'required' field is included
        assert "required" in tool_schema, (
            "Tool schema must include 'required' field from input_schema. "
            "Without it, Cy language validator treats ALL parameters as required, "
            "causing validation failures for optional parameters like 'search_base'."
        )

        # Verify required array contains only filter and attributes
        assert tool_schema["required"] == ["filter", "attributes"]
        assert "search_base" not in tool_schema["required"]

        # Verify return type from database tool (no framework override in this test)
        assert "return_type" in tool_schema
        # Database tool has output_schema with results array
        assert tool_schema["return_type"] == {
            "type": "object",
            "properties": {"results": {"type": "array"}},
        }

    @pytest.mark.asyncio
    async def test_load_tool_registry_handles_missing_required_field(
        self, mock_session
    ):
        """
        Test that load_tool_registry_async handles input_schema without 'required' field.

        Some tools may not have a 'required' field in their input_schema, which should
        result in an empty required array (all parameters optional).
        """
        # Create mock tool without 'required' field
        mock_tool = MagicMock()
        mock_tool.input_schema = {
            "type": "object",
            "properties": {
                "ip": {"type": "string", "description": "IP address"},
            },
            # No 'required' field - all parameters should be optional
        }
        mock_tool.output_schema = {"type": "object"}

        mock_component = MagicMock()
        mock_component.name = "virustotal::ip_reputation"
        mock_tool.component = mock_component

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_tool]
        mock_session.execute.return_value = mock_result
        mock_session.refresh = AsyncMock()

        tool_registry = await load_tool_registry_async(mock_session, "default")

        tool_schema = tool_registry["app::virustotal::ip_reputation"]

        # Verify 'required' field exists (framework has required: ['ip'])
        assert "required" in tool_schema
        # Framework virustotal::ip_reputation requires 'ip' parameter
        assert tool_schema["required"] == ["ip"]

        # Verify return type (framework tool has empty result_schema)
        assert "return_type" in tool_schema
        assert tool_schema["return_type"] == {}

    @pytest.mark.asyncio
    async def test_load_tool_registry_handles_all_required_parameters(
        self, mock_session
    ):
        """
        Test tool registry correctly includes required field when all parameters are required.
        """
        # Create mock tool where ALL parameters are required
        mock_tool = MagicMock()
        mock_tool.input_schema = {
            "type": "object",
            "properties": {
                "username": {"type": "string"},
                "password": {"type": "string"},
            },
            "required": ["username", "password"],  # All params required
        }
        mock_tool.output_schema = {"type": "boolean"}

        mock_component = MagicMock()
        mock_component.name = "ldap::authenticate"
        mock_tool.component = mock_component

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_tool]
        mock_session.execute.return_value = mock_result
        mock_session.refresh = AsyncMock()

        tool_registry = await load_tool_registry_async(mock_session, "default")

        tool_schema = tool_registry["app::ldap::authenticate"]

        # Verify 'required' contains all parameters
        assert "required" in tool_schema
        assert set(tool_schema["required"]) == {"username", "password"}

    @pytest.mark.asyncio
    async def test_load_tool_registry_includes_framework_tools_when_no_database_tools(
        self, mock_session
    ):
        """
        Test that load_tool_registry_async loads framework tools from manifests.

        Even when database has no KUTool records, the registry should include:
        1. Native functions (store_artifact)
        2. Framework tools from manifests (echo_edr, splunk, etc.)
        """
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        tool_registry = await load_tool_registry_async(mock_session, "default")

        # Should have native functions (store_artifact)
        assert "native::tools::store_artifact" in tool_registry

        # Should have framework integration tools loaded from manifests
        integration_tools = [k for k in tool_registry if k.startswith("app::")]
        assert len(integration_tools) > 0, (
            "Expected framework tools to be loaded from manifests even when database is empty"
        )

        # Should have echo_edr tools from manifests
        echo_edr_tools = [k for k in integration_tools if "echo_edr" in k]
        assert len(echo_edr_tools) > 0, (
            "Expected echo_edr tools to be loaded from framework manifests"
        )

    @pytest.mark.asyncio
    async def test_load_tool_registry_skips_malformed_database_tool_names(
        self, mock_session
    ):
        """
        Test that load_tool_registry_async skips DATABASE tools with malformed names.

        Framework tools from manifests are still loaded, but malformed database
        tools are skipped during the database loading phase.
        """
        # Create mock tool with malformed name (not integration::action format)
        mock_tool = MagicMock()
        mock_tool.input_schema = {"properties": {}}
        mock_tool.output_schema = {}

        mock_component = MagicMock()
        mock_component.name = "malformed_name_no_separator"  # Missing ::
        mock_tool.component = mock_component

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_tool]
        mock_session.execute.return_value = mock_result
        mock_session.refresh = AsyncMock()

        tool_registry = await load_tool_registry_async(mock_session, "default")

        # Should have native functions
        assert "native::tools::store_artifact" in tool_registry

        # Should have framework tools from manifests
        framework_tools = [k for k in tool_registry if k.startswith("app::")]
        assert len(framework_tools) > 0, (
            "Expected framework tools to be loaded from manifests"
        )

        # Malformed database tool should NOT be in registry
        assert "app::malformed_name_no_separator" not in tool_registry

    @pytest.mark.asyncio
    async def test_load_tool_registry_includes_store_artifact(self, mock_session):
        """
        Test that load_tool_registry_async includes store_artifact native function.

        This is a regression test for the bug where store_artifact was available at
        runtime but not in the compile-time tool registry, causing task creation to
        fail with "Tool 'store_artifact' not found" errors.
        """
        # Mock empty database query (no integration tools)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        # Load tool registry
        tool_registry = await load_tool_registry_async(mock_session, "default")

        # Verify store_artifact is in the registry
        assert "native::tools::store_artifact" in tool_registry, (
            "store_artifact must be in tool registry for compile-time validation. "
            "Without it, tasks using store_artifact fail with 'Tool not found' errors."
        )

        # Verify store_artifact has correct schema
        store_artifact = tool_registry["native::tools::store_artifact"]

        # Check parameters
        assert "parameters" in store_artifact
        assert "name" in store_artifact["parameters"]
        assert "artifact" in store_artifact["parameters"]
        assert "tags" in store_artifact["parameters"]
        assert "artifact_type" in store_artifact["parameters"]

        # Check required fields
        assert "required" in store_artifact
        assert "name" in store_artifact["required"]
        assert "artifact" in store_artifact["required"]
        # tags and artifact_type should NOT be required
        assert "tags" not in store_artifact["required"]
        assert "artifact_type" not in store_artifact["required"]

        # Check return type
        assert "return_type" in store_artifact
        assert store_artifact["return_type"]["type"] == "string"

    @pytest.mark.asyncio
    async def test_store_artifact_parameters_schema(self, mock_session):
        """Test that store_artifact has correct parameter types in registry."""
        # Mock empty database query
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        tool_registry = await load_tool_registry_async(mock_session, "default")
        store_artifact = tool_registry["native::tools::store_artifact"]

        # Verify name parameter
        assert store_artifact["parameters"]["name"]["type"] == "string"

        # Verify artifact parameter accepts string or object
        artifact_param = store_artifact["parameters"]["artifact"]
        assert "anyOf" in artifact_param
        types = [schema["type"] for schema in artifact_param["anyOf"]]
        assert "string" in types
        assert "object" in types

        # Verify tags parameter is object
        assert store_artifact["parameters"]["tags"]["type"] == "object"

        # Verify artifact_type parameter is string
        assert store_artifact["parameters"]["artifact_type"]["type"] == "string"

    @pytest.mark.asyncio
    async def test_load_tool_registry_includes_llm_functions(self, mock_session):
        """
        Test that load_tool_registry_async includes LLM native functions.

        Regression test for bug where LLM functions (llm_run, llm_summarize, etc.)
        were available at runtime but not in compile-time tool registry, causing
        task creation to fail with "Tool 'llm_run' not found" errors.
        """
        # Mock empty database query (no integration tools)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        # Load tool registry
        tool_registry = await load_tool_registry_async(mock_session, "default")

        # Verify llm_run is in registry
        assert "native::llm::llm_run" in tool_registry, (
            "llm_run must be in tool registry for compile-time validation. "
            "Without it, tasks using llm_run fail with 'Tool not found' errors."
        )

        llm_run = tool_registry["native::llm::llm_run"]

        # Check parameters
        assert "parameters" in llm_run
        assert "prompt" in llm_run["parameters"]
        assert llm_run["parameters"]["prompt"]["type"] == "string"

        # Optional parameters
        assert "model" in llm_run["parameters"]
        assert "temperature" in llm_run["parameters"]
        assert "max_tokens" in llm_run["parameters"]
        assert "integration_id" in llm_run["parameters"]

        # Check required fields - only prompt is required
        assert "required" in llm_run
        assert "prompt" in llm_run["required"]
        assert len(llm_run["required"]) == 1

        # Check return type
        assert "return_type" in llm_run
        assert llm_run["return_type"]["type"] == "string"

    @pytest.mark.asyncio
    async def test_load_tool_registry_includes_all_llm_functions(self, mock_session):
        """Test that all LLM functions are registered in tool registry."""
        # Mock empty database query
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        tool_registry = await load_tool_registry_async(mock_session, "default")

        # Verify all LLM functions are present
        expected_llm_functions = [
            "native::llm::llm_run",
            "native::llm::llm_summarize",
            "native::llm::llm_extract",
            "native::llm::llm_evaluate_results",
        ]

        for func_name in expected_llm_functions:
            assert func_name in tool_registry, (
                f"LLM function '{func_name}' must be in tool registry. "
                f"Available at runtime but missing from compile-time registry causes validation errors."
            )

            # Verify each has required fields
            func_schema = tool_registry[func_name]
            assert "parameters" in func_schema
            assert "required" in func_schema
            assert "return_type" in func_schema

    @pytest.mark.asyncio
    async def test_llm_summarize_schema(self, mock_session):
        """Test llm_summarize has correct schema."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        tool_registry = await load_tool_registry_async(mock_session, "default")
        llm_summarize = tool_registry["native::llm::llm_summarize"]

        # Verify parameters
        assert "text" in llm_summarize["parameters"]
        assert llm_summarize["parameters"]["text"]["type"] == "string"
        assert "max_words" in llm_summarize["parameters"]
        assert (
            llm_summarize["parameters"]["max_words"]["type"] == "number"
        )  # integer literals are typed as number in cy-language
        assert "integration_id" in llm_summarize["parameters"]

        # Verify only text is required
        assert llm_summarize["required"] == ["text"]

        # Verify return type
        assert llm_summarize["return_type"]["type"] == "string"

    @pytest.mark.asyncio
    async def test_llm_extract_schema(self, mock_session):
        """Test llm_extract has correct schema."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        tool_registry = await load_tool_registry_async(mock_session, "default")
        llm_extract = tool_registry["native::llm::llm_extract"]

        # Verify parameters
        assert "text" in llm_extract["parameters"]
        assert llm_extract["parameters"]["text"]["type"] == "string"
        assert "fields" in llm_extract["parameters"]
        assert llm_extract["parameters"]["fields"]["type"] == "array"
        assert "integration_id" in llm_extract["parameters"]

        # Verify text and fields are required
        assert set(llm_extract["required"]) == {"text", "fields"}

        # Verify return type
        assert llm_extract["return_type"]["type"] == "object"

    @pytest.mark.asyncio
    async def test_llm_evaluate_results_schema(self, mock_session):
        """Test llm_evaluate_results has correct schema."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        tool_registry = await load_tool_registry_async(mock_session, "default")
        llm_eval = tool_registry["native::llm::llm_evaluate_results"]

        # Verify parameters
        assert "results" in llm_eval["parameters"]
        # results accepts string or object
        assert "anyOf" in llm_eval["parameters"]["results"]
        assert "criteria" in llm_eval["parameters"]
        assert "integration_id" in llm_eval["parameters"]

        # Verify only results is required
        assert llm_eval["required"] == ["results"]

        # Verify return type structure
        assert llm_eval["return_type"]["type"] == "object"
        assert "properties" in llm_eval["return_type"]
        assert "summary" in llm_eval["return_type"]["properties"]
        assert "findings" in llm_eval["return_type"]["properties"]
        assert "issues" in llm_eval["return_type"]["properties"]
        assert "recommendations" in llm_eval["return_type"]["properties"]

    @pytest.mark.asyncio
    async def test_load_tool_registry_includes_all_native_functions(self, mock_session):
        """
        Test that all native functions from runtime modules are registered.

        Ensures compile-time validation matches runtime capabilities for:
        - Tools (store_artifact)
        - LLM (llm_run, llm_summarize, llm_extract, llm_evaluate_results)
        - Alert (alert_read)
        - Task (task_run)
        - KU (table_read, table_write, document_read)
        """
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        tool_registry = await load_tool_registry_async(mock_session, "default")

        # All native function namespaces and their functions
        expected_native_functions = {
            # Tools namespace
            "native::tools::store_artifact",
            # LLM namespace
            "native::llm::llm_run",
            "native::llm::llm_summarize",
            "native::llm::llm_extract",
            "native::llm::llm_evaluate_results",
            # Alert namespace
            "native::alert::alert_read",
            # Task namespace
            "native::task::task_run",
            # KU namespace
            "native::ku::table_read",
            "native::ku::table_write",
            "native::ku::document_read",
        }

        for func_fqn in expected_native_functions:
            assert func_fqn in tool_registry, (
                f"Native function '{func_fqn}' must be in tool registry. "
                f"All runtime native functions need compile-time registration."
            )

            # Verify structure
            func_schema = tool_registry[func_fqn]
            assert "parameters" in func_schema
            assert "required" in func_schema
            assert "return_type" in func_schema

    @pytest.mark.asyncio
    async def test_alert_read_schema(self, mock_session):
        """Test alert_read has correct schema with OCSF format (AlertResponse Pydantic schema)."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        tool_registry = await load_tool_registry_async(mock_session, "default")
        alert_read = tool_registry["native::alert::alert_read"]

        # Verify parameters
        assert "alert_id" in alert_read["parameters"]
        assert alert_read["parameters"]["alert_id"]["type"] == "string"

        # Verify alert_id is required
        assert alert_read["required"] == ["alert_id"]

        # Verify return type is dynamically loaded from AlertResponse Pydantic schema
        return_type = alert_read["return_type"]
        assert "type" in return_type
        assert return_type["type"] == "object"

        # Verify key OCSF fields are present in schema properties
        assert "properties" in return_type, (
            "AlertResponse schema should have properties"
        )
        properties = return_type["properties"]

        # Check key fields from AlertResponse (fields from both AlertResponse and AlertBase)
        expected_fields = [
            "alert_id",  # From AlertResponse
            "tenant_id",  # From AlertResponse
            "human_readable_id",  # From AlertResponse
            "analysis_status",  # From AlertResponse
            "raw_data_hash",  # From AlertResponse (renamed from content_hash)
            "created_at",  # From AlertResponse
            "updated_at",  # From AlertResponse
            "title",  # From AlertBase
            "severity",  # From AlertBase
            "triggering_event_time",  # From AlertBase
            "source_vendor",  # From AlertBase
            "source_product",  # From AlertBase
            "raw_data",  # From AlertBase (OCSF: renamed from raw_alert)
        ]

        for field in expected_fields:
            assert field in properties, (
                f"Field '{field}' missing from AlertResponse schema. "
                f"Expected dynamically loaded Pydantic schema to include all AlertResponse fields."
            )

    @pytest.mark.asyncio
    async def test_task_run_schema(self, mock_session):
        """Test task_run has correct schema."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        tool_registry = await load_tool_registry_async(mock_session, "default")
        task_run = tool_registry["native::task::task_run"]

        # Verify parameters
        assert "task_name" in task_run["parameters"]
        assert "input_data" in task_run["parameters"]
        assert "full_result" in task_run["parameters"]

        # Verify only task_name is required
        assert task_run["required"] == ["task_name"]

        # Verify return type accepts multiple types
        assert "anyOf" in task_run["return_type"]

    @pytest.mark.asyncio
    async def test_table_read_schema(self, mock_session):
        """Test table_read has correct schema matching cy_ku_functions.py signature."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        tool_registry = await load_tool_registry_async(mock_session, "default")
        table_read = tool_registry["native::ku::table_read"]

        # Verify parameters match signature: table_read(name, id, max_rows=1000, max_bytes=1_000_000)
        assert "name" in table_read["parameters"]
        assert "id" in table_read["parameters"]
        assert "max_rows" in table_read["parameters"]
        assert "max_bytes" in table_read["parameters"]
        assert table_read["parameters"]["max_rows"]["type"] == "number"
        assert table_read["parameters"]["max_bytes"]["type"] == "number"

        # Verify nothing is strictly required (name OR id can be provided, validated at runtime)
        assert table_read["required"] == []

        # Verify return type is array of objects
        assert table_read["return_type"]["type"] == "array"
        assert table_read["return_type"]["items"]["type"] == "object"

    @pytest.mark.asyncio
    async def test_document_read_schema(self, mock_session):
        """Test document_read has correct schema matching cy_ku_functions.py signature."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        tool_registry = await load_tool_registry_async(mock_session, "default")
        document_read = tool_registry["native::ku::document_read"]

        # Verify parameters match signature: document_read(name, id, max_characters=100_000)
        assert "name" in document_read["parameters"]
        assert "id" in document_read["parameters"]
        assert "max_characters" in document_read["parameters"]
        assert document_read["parameters"]["max_characters"]["type"] == "number"

        # Verify nothing is strictly required
        assert document_read["required"] == []

        # Verify return type is string
        assert document_read["return_type"]["type"] == "string"

    @pytest.mark.asyncio
    async def test_no_ai_archetype_collision_with_native_tools(self, mock_session):
        """
        AI archetype tools must not collide with native LLM functions.

        AI integrations (anthropic_agent, openai, gemini) expose llm_run/llm_chat
        as framework tools. These must be excluded from the compile-time registry
        because native::llm::llm_run already handles them. Having both causes
        AmbiguousToolError in the Cy compiler when a script calls bare llm_run().
        """
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        tool_registry = await load_tool_registry_async(mock_session, "default")

        # Native LLM functions should be present
        assert "native::llm::llm_run" in tool_registry
        assert "native::llm::llm_summarize" in tool_registry

        # Framework tools whose short name collides with a native function
        # must NOT appear in the registry.
        # e.g. app::anthropic_agent::llm_run collides with native::llm::llm_run
        from analysi.services.native_tools_registry import NATIVE_TOOL_METADATA

        native_short_names = {fqn.rsplit("::", 1)[-1] for fqn in NATIVE_TOOL_METADATA}

        colliding_tools = [
            fqn
            for fqn in tool_registry
            if fqn.startswith("app::") and fqn.rsplit("::", 1)[-1] in native_short_names
        ]
        assert colliding_tools == [], (
            f"Framework tools must not collide with native functions to avoid "
            f"AmbiguousToolError. Found colliding tools: {colliding_tools}"
        )
