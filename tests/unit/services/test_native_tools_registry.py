"""
Unit tests for native tools registry with signature extraction.

Tests the DRY solution for native function registration that:
1. Extracts function signatures from actual implementations
2. Combines with manual metadata (descriptions, return types)
3. Validates that all runtime functions are registered
"""

from typing import ClassVar


class TestNativeFunctionSignatureExtraction:
    """Test extracting function signatures from native function modules."""

    def test_extract_llm_run_signature(self):
        """
        Test extracting signature from CyLLMFunctions.llm_run().

        Should detect:
        - prompt: str (required)
        - model: str | None (optional)
        - temperature: float | None (optional)
        - max_tokens: int | None (optional)
        - integration_id: str | None (optional)
        """
        from analysi.services.native_tools_registry import extract_function_signature

        signature = extract_function_signature(
            "analysi.services.cy_llm_functions", "CyLLMFunctions", "llm_run"
        )

        # Should extract parameters
        assert "prompt" in signature["parameters"]
        assert signature["parameters"]["prompt"]["type"] == "string"

        assert "model" in signature["parameters"]
        assert signature["parameters"]["model"]["type"] == "string"

        assert "temperature" in signature["parameters"]
        assert signature["parameters"]["temperature"]["type"] == "number"

        assert "max_tokens" in signature["parameters"]
        assert signature["parameters"]["max_tokens"]["type"] == "number"

        assert "integration_id" in signature["parameters"]
        assert signature["parameters"]["integration_id"]["type"] == "string"

        # Should detect required parameters (only prompt is required)
        assert signature["required"] == ["prompt"]

    def test_extract_store_artifact_signature(self):
        """
        Test extracting signature from CyArtifactFunctions.store_artifact().

        Should detect:
        - name: str (required)
        - artifact: str | bytes | dict (required, anyOf types)
        - tags: dict | None (optional)
        - artifact_type: str | None (optional)
        """
        from analysi.services.native_tools_registry import extract_function_signature

        signature = extract_function_signature(
            "analysi.services.cy_functions", "CyArtifactFunctions", "store_artifact"
        )

        # Should extract parameters
        assert "name" in signature["parameters"]
        assert "artifact" in signature["parameters"]
        assert "tags" in signature["parameters"]
        assert "artifact_type" in signature["parameters"]

        # artifact should support multiple types (anyOf)
        assert "anyOf" in signature["parameters"]["artifact"]

        # Should detect required parameters (name and artifact)
        assert set(signature["required"]) == {"name", "artifact"}

    def test_extract_table_read_signature(self):
        """
        Test extracting signature from CyKUFunctions.table_read().

        Should detect:
        - name: str | None (optional)
        - id: str | None (optional)
        - max_rows: int = 1000 (optional with default)
        - max_bytes: int = 1_000_000 (optional with default)

        Note: Runtime validates that at least one of name or id is provided.
        """
        from analysi.services.native_tools_registry import extract_function_signature

        signature = extract_function_signature(
            "analysi.services.cy_ku_functions", "CyKUFunctions", "table_read"
        )

        # Should extract all parameters
        assert "name" in signature["parameters"]
        assert "id" in signature["parameters"]
        assert "max_rows" in signature["parameters"]
        assert "max_bytes" in signature["parameters"]

        # Should detect no required parameters (runtime validates name OR id)
        assert signature["required"] == []


class TestNativeFunctionMetadata:
    """Test manual metadata for native functions (descriptions, return types)."""

    def test_metadata_includes_all_native_functions(self):
        """
        Test that NATIVE_TOOL_METADATA includes metadata for all 10 native functions.

        This prevents forgetting to add metadata when new native functions are created.
        """
        from analysi.services.native_tools_registry import NATIVE_TOOL_METADATA

        expected_functions = {
            "native::tools::store_artifact",
            "native::llm::llm_run",
            "native::llm::llm_summarize",
            "native::llm::llm_extract",
            "native::llm::llm_evaluate_results",
            "native::alert::alert_read",
            "native::task::task_run",
            "native::ku::table_read",
            "native::ku::table_write",
            "native::ku::document_read",
        }

        for func_fqn in expected_functions:
            assert func_fqn in NATIVE_TOOL_METADATA, (
                f"Native function '{func_fqn}' missing from NATIVE_TOOL_METADATA. "
                f"Add metadata entry with description and return_type."
            )

            metadata = NATIVE_TOOL_METADATA[func_fqn]
            assert "description" in metadata, f"{func_fqn} must have description"
            assert "return_type" in metadata, f"{func_fqn} must have return_type"

    def test_metadata_has_correct_structure(self):
        """Test that metadata entries have the correct structure."""
        from analysi.services.native_tools_registry import NATIVE_TOOL_METADATA

        llm_run_meta = NATIVE_TOOL_METADATA["native::llm::llm_run"]

        # Should have description
        assert isinstance(llm_run_meta["description"], str)
        assert len(llm_run_meta["description"]) > 10, "Description should be meaningful"

        # Should have return_type
        assert isinstance(llm_run_meta["return_type"], dict)
        assert "type" in llm_run_meta["return_type"]


class TestNativeToolsRegistryGeneration:
    """Test combining signatures + metadata to generate tool registry entries."""

    def test_generate_registry_entry_for_llm_run(self):
        """
        Test generating complete registry entry for llm_run.

        Should combine:
        - Signature extraction (parameters, required)
        - Manual metadata (description, return_type)
        """
        from analysi.services.native_tools_registry import generate_native_tool_entry

        entry = generate_native_tool_entry("native::llm::llm_run")

        # Should have all required fields
        assert "description" in entry
        assert "parameters" in entry
        assert "required" in entry
        assert "return_type" in entry

        # Description from metadata
        assert "LLM" in entry["description"] or "llm" in entry["description"].lower()

        # Parameters from signature
        assert "prompt" in entry["parameters"]
        assert entry["parameters"]["prompt"]["type"] == "string"

        # Required from signature
        assert "prompt" in entry["required"]

        # Return type from metadata
        assert entry["return_type"]["type"] == "string"

    def test_generate_registry_entry_for_store_artifact(self):
        """Test generating complete registry entry for store_artifact."""
        from analysi.services.native_tools_registry import generate_native_tool_entry

        entry = generate_native_tool_entry("native::tools::store_artifact")

        # Should have all required fields
        assert "description" in entry
        assert "parameters" in entry
        assert "required" in entry
        assert "return_type" in entry

        # Parameters from signature
        assert "name" in entry["parameters"]
        assert "artifact" in entry["parameters"]

        # Required from signature
        assert set(entry["required"]) == {"name", "artifact"}

        # Return type from metadata
        assert entry["return_type"]["type"] == "string"

    def test_get_all_native_tools_registry(self):
        """
        Test getting complete native tools registry for all native functions.

        This replaces the manual hardcoded entries in cy_tool_registry.py.
        """
        from analysi.services.native_tools_registry import get_native_tools_registry

        registry = get_native_tools_registry()

        expected_functions = {
            "native::tools::store_artifact",
            "native::tools::format_timestamp",
            "native::tools::sleep",
            "native::llm::llm_run",
            "native::llm::llm_summarize",
            "native::llm::llm_extract",
            "native::llm::llm_evaluate_results",
            "native::alert::alert_read",
            "native::alert::enrich_alert",
            "native::task::task_run",
            "native::ku::table_read",
            "native::ku::table_write",
            "native::ku::document_read",
            "native::ku::table_read_via_id",
            "native::ku::table_write_via_id",
            "native::ku::document_read_via_id",
            "native::ku::index_create",
            "native::ku::index_add",
            "native::ku::index_add_with_metadata",
            "native::ku::index_search",
            "native::ku::index_delete",
            # Project Skaros: OCSF alert navigation helpers
            "native::ocsf::get_primary_entity_type",
            "native::ocsf::get_primary_entity_value",
            "native::ocsf::get_primary_user",
            "native::ocsf::get_primary_device",
            "native::ocsf::get_primary_observable_type",
            "native::ocsf::get_primary_observable_value",
            "native::ocsf::get_primary_observable",
            "native::ocsf::get_observables",
            "native::ocsf::get_src_ip",
            "native::ocsf::get_dst_ip",
            "native::ocsf::get_dst_domain",
            "native::ocsf::get_http_method",
            "native::ocsf::get_user_agent",
            "native::ocsf::get_http_response_code",
            "native::ocsf::get_url",
            "native::ocsf::get_url_path",
            "native::ocsf::get_cve_ids",
            "native::ocsf::get_label",
            # Project Symi: Ingest + checkpoint functions
            "native::ingest::ingest_alerts",
            "native::ingest::get_checkpoint",
            "native::ingest::set_checkpoint",
            "native::ingest::default_lookback",
        }

        assert set(registry.keys()) == expected_functions

        # Each entry should have complete structure
        for func_fqn, entry in registry.items():
            assert "description" in entry, f"{func_fqn} missing description"
            assert "parameters" in entry, f"{func_fqn} missing parameters"
            assert "required" in entry, f"{func_fqn} missing required"
            assert "return_type" in entry, f"{func_fqn} missing return_type"


class TestCompleteness:
    """Guard: every runtime Cy function must have a compile-time registry entry.

    Without this, a function can be added to a create_cy_* factory (runtime)
    but missing from NATIVE_TOOL_METADATA (compile-time validation), causing
    scripts that use it to fail on save via the API.

    This test calls every factory with mocks and checks that ALL returned
    keys have a matching entry in NATIVE_TOOL_METADATA.
    """

    # Map of (factory_module, factory_function, namespace, factory_args_style)
    # factory_args_style:
    #   "llm"        -> create_cy_llm_functions(mock_factory, {}) returns (dict, instance)
    #   "artifact"   -> create_cy_artifact_functions(mock_service, {})
    #   "session"    -> create_cy_*(mock_session, "default", {})
    #   "context"    -> create_cy_*(execution_context)
    #   "none"       -> create_cy_*()
    FACTORIES: ClassVar[list[tuple[str, str, str, str]]] = [
        (
            "analysi.services.cy_llm_functions",
            "create_cy_llm_functions",
            "native::llm",
            "llm",
        ),
        (
            "analysi.services.cy_functions",
            "create_cy_artifact_functions",
            "native::tools",
            "artifact",
        ),
        (
            "analysi.services.cy_ku_functions",
            "create_cy_ku_functions",
            "native::ku",
            "session",
        ),
        (
            "analysi.services.cy_index_functions",
            "create_cy_index_functions",
            "native::ku",
            "index",
        ),
        (
            "analysi.services.cy_alert_functions",
            "create_cy_alert_functions",
            "native::alert",
            "session",
        ),
        (
            "analysi.services.cy_task_functions",
            "create_cy_task_functions",
            "native::task",
            "session",
        ),
        (
            "analysi.services.cy_enrichment_functions",
            "create_cy_enrichment_functions",
            "native::alert",
            "context",
        ),
        (
            "analysi.services.cy_ocsf_helpers",
            "create_cy_ocsf_helpers",
            "native::ocsf",
            "none",
        ),
        (
            "analysi.services.cy_ingest_functions",
            "create_cy_ingest_functions",
            "native::ingest",
            "session",
        ),
    ]

    def _call_factory(self, module_path, func_name, style):
        """Call a factory with appropriate mocks and return the function dict."""
        import importlib
        from unittest.mock import AsyncMock, MagicMock

        module = importlib.import_module(module_path)
        factory = getattr(module, func_name)

        if style == "llm":
            result = factory(MagicMock(), {})
            return result[0]  # (functions_dict, instance)
        if style == "artifact":
            return factory(MagicMock(), {})
        if style == "session":
            return factory(AsyncMock(), "default", {})
        if style == "index":
            return factory(AsyncMock(), "default", {}, MagicMock())
        if style == "context":
            return factory({})
        if style == "none":
            return factory()
        raise ValueError(f"Unknown factory style: {style}")

    def test_all_runtime_functions_registered_in_metadata(self):
        """Every key returned by every create_cy_* factory must be in NATIVE_TOOL_METADATA.

        This is the structural guard that would have caught the Symi ingest
        functions gap (and the _via_id / _with_metadata gaps).
        """
        from analysi.services.native_tools_registry import NATIVE_TOOL_METADATA

        metadata_short_names = {fqn.split("::")[-1] for fqn in NATIVE_TOOL_METADATA}

        missing = []

        for module_path, func_name, namespace, style in self.FACTORIES:
            runtime_functions = self._call_factory(module_path, func_name, style)
            for bare_name in runtime_functions:
                # Skip FQN keys (some factories register both "sleep" and "native::tools::sleep")
                if "::" in bare_name:
                    continue
                if bare_name not in metadata_short_names:
                    missing.append(
                        f"  {bare_name} (from {func_name}) — "
                        f"add '{namespace}::{bare_name}' to NATIVE_TOOL_METADATA"
                    )

        assert not missing, (
            "Runtime Cy functions missing from compile-time NATIVE_TOOL_METADATA.\n"
            "Scripts using these will fail validation on save.\n"
            "Missing:\n" + "\n".join(missing)
        )

    def test_time_and_sleep_functions_registered(self):
        """Time and sleep functions are loaded inline (not via create_cy_*).

        Verify they're in the registry too.
        """
        from analysi.services.native_tools_registry import NATIVE_TOOL_METADATA

        metadata_short_names = {fqn.split("::")[-1] for fqn in NATIVE_TOOL_METADATA}

        for func_name in ["format_timestamp", "sleep"]:
            assert func_name in metadata_short_names, (
                f"Time/sleep function '{func_name}' is loaded at runtime but "
                f"missing from NATIVE_TOOL_METADATA"
            )
