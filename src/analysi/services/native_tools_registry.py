"""
Native Tools Registry - DRY Solution for Native Function Registration.

This module provides automatic registration of native Cy functions by:
1. Extracting function signatures using Python's inspect module
2. Combining with manual metadata (descriptions, return types)
3. Validating completeness (ensures all runtime functions are registered)

This replaces the manual hardcoded registration in cy_tool_registry.py,
reducing duplication and preventing forgotten registrations.
"""

import importlib
import inspect
from typing import Any, get_args, get_origin


# Short names of native tools (e.g., "llm_run", "store_artifact").
# Used by cy_tool_registry and task_execution to skip framework tools
# that collide with native functions (e.g., app::anthropic_agent::llm_run).
def get_native_short_names() -> frozenset[str]:
    """Return the short (unqualified) names of all native tools."""
    return frozenset(fqn.rsplit("::", 1)[-1] for fqn in NATIVE_TOOL_METADATA)


# Manual metadata for native functions (descriptions and return types)
# This is the ONLY place where manual configuration is needed
NATIVE_TOOL_METADATA = {
    "native::tools::store_artifact": {
        "description": "Store investigation artifacts (timelines, graphs, tables, files) for later retrieval and reporting",
        "module": "analysi.services.cy_functions",
        "class_name": "CyArtifactFunctions",
        "method_name": "store_artifact",
        "return_type": {"type": "string", "description": "Artifact ID from database"},
    },
    "native::llm::llm_run": {
        "description": "Execute LLM prompts using configured AI integrations (OpenAI, etc.) for analysis, decision-making, and content generation",
        "module": "analysi.services.cy_llm_functions",
        "class_name": "CyLLMFunctions",
        "method_name": "llm_run",
        "return_type": {"type": "string", "description": "LLM response as string"},
    },
    "native::llm::llm_summarize": {
        "description": "Summarize text using LLM to create concise overviews of logs, events, or investigation findings",
        "module": "analysi.services.cy_llm_functions",
        "class_name": "CyLLMFunctions",
        "method_name": "llm_summarize",
        "return_type": {"type": "string", "description": "Summary as string"},
    },
    "native::llm::llm_extract": {
        "description": "Extract structured data from unstructured text using LLM (e.g., extract IOCs, dates, or entities from logs)",
        "module": "analysi.services.cy_llm_functions",
        "class_name": "CyLLMFunctions",
        "method_name": "llm_extract",
        "return_type": {
            "type": "object",
            "description": "Dictionary of extracted fields with field names as keys",
        },
    },
    "native::llm::llm_evaluate_results": {
        "description": "Use LLM to evaluate investigation results against criteria (e.g., assess severity, determine next steps)",
        "module": "analysi.services.cy_llm_functions",
        "class_name": "CyLLMFunctions",
        "method_name": "llm_evaluate_results",
        "return_type": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "Summary of results"},
                "findings": {"type": "array", "description": "Key findings"},
                "issues": {"type": "array", "description": "Issues or concerns"},
                "recommendations": {"type": "array", "description": "Recommendations"},
            },
            "description": "Evaluation results as structured object",
        },
        # Override parameter schemas (signature has 'Any' which can't be auto-extracted)
        "parameter_overrides": {
            "results": {
                "anyOf": [
                    {"type": "string"},
                    {"type": "object"},
                ],
                "description": "Results to evaluate (will be JSON serialized if object)",
            }
        },
    },
    "native::alert::alert_read": {
        "description": "Retrieve alert details in OCSF Detection Finding format by alert ID",
        "module": "analysi.services.cy_alert_functions",
        "class_name": "CyAlertFunctions",
        "method_name": "alert_read",
        "return_type": None,  # Will be loaded from AlertResponse Pydantic schema dynamically
    },
    "native::task::task_run": {
        "description": "Execute another task from within the current task, enabling task composition and workflow orchestration",
        "module": "analysi.services.cy_task_functions",
        "class_name": "CyTaskFunctions",
        "method_name": "task_run",
        "return_type": {
            "anyOf": [
                {
                    "type": "object",
                    "description": "Task output or full result with status",
                },
                {"type": "string"},
                {"type": "array"},
            ]
        },
    },
    "native::ku::table_read": {
        "description": "Read data from a Knowledge Unit table (e.g., asset lists, watchlists, lookup tables) by name or ID",
        "module": "analysi.services.cy_ku_functions",
        "class_name": "CyKUFunctions",
        "method_name": "table_read",
        "return_type": {
            "type": "array",
            "items": {"type": "object"},
            "description": "List of dictionaries, each representing a table row",
        },
    },
    "native::ku::table_write": {
        "description": "Write data to a Knowledge Unit table, either replacing existing data or appending to it",
        "module": "analysi.services.cy_ku_functions",
        "class_name": "CyKUFunctions",
        "method_name": "table_write",
        "return_type": {"type": "boolean", "description": "True if successful"},
    },
    "native::ku::document_read": {
        "description": "Read content from a Knowledge Unit document (e.g., runbooks, procedures, reference docs) by name or ID",
        "module": "analysi.services.cy_ku_functions",
        "class_name": "CyKUFunctions",
        "method_name": "document_read",
        "return_type": {"type": "string", "description": "Document content as string"},
    },
    # UUID-based access variants (call same methods with id= instead of name=)
    "native::ku::table_read_via_id": {
        "description": "Read data from a Knowledge Unit table by UUID",
        "module": "analysi.services.cy_ku_functions",
        "class_name": "CyKUFunctions",
        "method_name": "table_read",
        "parameters": {"id": {"type": "string", "description": "UUID of the table"}},
        "return_type": {
            "type": "array",
            "items": {"type": "object"},
            "description": "List of dictionaries, each representing a table row",
        },
    },
    "native::ku::table_write_via_id": {
        "description": "Write data to a Knowledge Unit table by UUID",
        "module": "analysi.services.cy_ku_functions",
        "class_name": "CyKUFunctions",
        "method_name": "table_write",
        "parameters": {
            "id": {"type": "string", "description": "UUID of the table"},
            "data": {
                "type": "array",
                "items": {"type": "object"},
                "description": "Rows to write",
            },
            "mode": {
                "type": "string",
                "description": "Write mode: 'replace' or 'append'",
            },
        },
        "return_type": {"type": "boolean", "description": "True if successful"},
    },
    "native::ku::document_read_via_id": {
        "description": "Read content from a Knowledge Unit document by UUID",
        "module": "analysi.services.cy_ku_functions",
        "class_name": "CyKUFunctions",
        "method_name": "document_read",
        "parameters": {"id": {"type": "string", "description": "UUID of the document"}},
        "return_type": {"type": "string", "description": "Document content as string"},
    },
    # Project Paros — Knowledge Index functions
    "native::ku::index_create": {
        "description": "Create a Knowledge Unit index collection if it doesn't exist (idempotent). No-op if already exists.",
        "module": "analysi.services.cy_index_functions",
        "class_name": "CyIndexFunctions",
        "method_name": "index_create",
        "return_type": {
            "type": "boolean",
            "description": "True always (created or already existed)",
        },
    },
    "native::ku::index_add": {
        "description": "Add text to a Knowledge Unit index collection for semantic search (auto-embeds, idempotent — duplicate content is silently skipped)",
        "module": "analysi.services.cy_index_functions",
        "class_name": "CyIndexFunctions",
        "method_name": "index_add",
        "return_type": {
            "type": "boolean",
            "description": "True if entry added successfully",
        },
    },
    "native::ku::index_add_with_metadata": {
        "description": "Add text with metadata and source reference to a Knowledge Unit index collection",
        "module": "analysi.services.cy_index_functions",
        "class_name": "CyIndexFunctions",
        "method_name": "index_add",
        "parameters": {
            "name": {"type": "string", "description": "Index collection name"},
            "content": {"type": "string", "description": "Text content to index"},
            "metadata": {"type": "object", "description": "Arbitrary metadata dict"},
            "source_ref": {
                "type": "string",
                "description": "Source reference identifier",
            },
        },
        "return_type": {
            "type": "boolean",
            "description": "True if entry added successfully",
        },
    },
    "native::ku::index_search": {
        "description": "Search a Knowledge Unit index collection by semantic similarity (auto-embeds query)",
        "module": "analysi.services.cy_index_functions",
        "class_name": "CyIndexFunctions",
        "method_name": "index_search",
        "return_type": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "entry_id": {"type": "string"},
                    "content": {"type": "string"},
                    "score": {"type": "number"},
                    "metadata": {"type": "object"},
                    "source_ref": {"type": "string"},
                },
            },
            "description": "List of search results ordered by similarity score",
        },
    },
    "native::ku::index_delete": {
        "description": "Delete an entry from a Knowledge Unit index collection by entry ID",
        "module": "analysi.services.cy_index_functions",
        "class_name": "CyIndexFunctions",
        "method_name": "index_delete",
        "return_type": {"type": "boolean", "description": "True if entry was deleted"},
    },
    # Time functions - TODO: Migrate to cy-language repo (see docs/TODO.md)
    "native::tools::format_timestamp": {
        "description": "Convert ISO 8601 timestamp to various formats (splunk, iso, date, datetime, clf) for security integrations",
        "module": "analysi.services.cy_time_functions",
        "class_name": "CyTimeFunctions",
        "method_name": "format_timestamp",
        "return_type": {"type": "string", "description": "Formatted timestamp string"},
    },
    "native::tools::sleep": {
        "description": "Pause task execution for a specified number of seconds. Useful for testing job lifecycle (retry, cancellation, stuck detection).",
        "module": "analysi.services.cy_sleep_functions",
        "class_name": "CySleepFunctions",
        "method_name": "sleep",
        "return_type": {"type": "boolean", "description": "True when sleep completes"},
    },
    "native::alert::enrich_alert": {
        "description": "Add enrichment data to an alert dict under the task's cy_name key (or a custom key). Returns the modified alert.",
        "module": "analysi.services.cy_enrichment_functions",
        "class_name": "CyEnrichmentFunctions",
        "method_name": "enrich_alert",
        "parameters": {
            "alert": {
                "type": "object",
                "description": "The alert dict to enrich (typically `input` in a Cy script)",
            },
            "enrichment_data": {
                "anyOf": [
                    {"type": "object"},
                    {"type": "array"},
                    {"type": "string"},
                    {"type": "number"},
                    {"type": "null"},
                ],
                "description": "Data to store under alert['enrichments'][key]",
            },
            "key_name": {
                "anyOf": [{"type": "string"}, {"type": "null"}],
                "description": "Optional custom enrichment key. Defaults to the task's cy_name.",
            },
        },
        "return_type": {
            "type": "object",
            "description": "The alert dict with the enrichment added under alert['enrichments'][key]",
        },
    },
    # ── Project Skaros: OCSF Alert Navigation Helpers ──────────────────
    "native::ocsf::get_primary_entity_type": {
        "description": "Get the type of the primary risk entity ('user', 'device', or None). Works with OCSF alert format.",
        "module": "analysi.services.cy_ocsf_helpers",
        "class_name": "CyOCSFHelpers",
        "method_name": "get_primary_entity_type",
        "return_type": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
    "native::ocsf::get_primary_entity_value": {
        "description": "Get the value of the primary risk entity (username, hostname, etc.). Works with OCSF alert format.",
        "module": "analysi.services.cy_ocsf_helpers",
        "class_name": "CyOCSFHelpers",
        "method_name": "get_primary_entity_value",
        "return_type": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
    "native::ocsf::get_primary_user": {
        "description": "Extract the primary user from the alert. Returns username string or None if no user entity.",
        "module": "analysi.services.cy_ocsf_helpers",
        "class_name": "CyOCSFHelpers",
        "method_name": "get_primary_user",
        "return_type": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
    "native::ocsf::get_primary_device": {
        "description": "Extract the primary device from the alert. Returns hostname/name/IP string or None.",
        "module": "analysi.services.cy_ocsf_helpers",
        "class_name": "CyOCSFHelpers",
        "method_name": "get_primary_device",
        "return_type": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
    "native::ocsf::get_primary_observable_type": {
        "description": "Get the type of the primary observable/IOC ('ip', 'domain', 'filehash', etc.). Works with OCSF alert format.",
        "module": "analysi.services.cy_ocsf_helpers",
        "class_name": "CyOCSFHelpers",
        "method_name": "get_primary_observable_type",
        "return_type": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
    "native::ocsf::get_primary_observable_value": {
        "description": "Get the value of the primary observable/IOC (IP address, domain name, hash, etc.).",
        "module": "analysi.services.cy_ocsf_helpers",
        "class_name": "CyOCSFHelpers",
        "method_name": "get_primary_observable_value",
        "return_type": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
    "native::ocsf::get_primary_observable": {
        "description": "Get the primary observable as a dict with 'type' and 'value' keys. Optionally filter by type name.",
        "module": "analysi.services.cy_ocsf_helpers",
        "class_name": "CyOCSFHelpers",
        "method_name": "get_primary_observable",
        "return_type": {"anyOf": [{"type": "object"}, {"type": "null"}]},
    },
    "native::ocsf::get_observables": {
        "description": "Get all observables/IOCs from the alert as a list of dicts. Optionally filter by type name (e.g., 'ip', 'domain').",
        "module": "analysi.services.cy_ocsf_helpers",
        "class_name": "CyOCSFHelpers",
        "method_name": "get_observables",
        "return_type": {"type": "array", "items": {"type": "object"}},
    },
    "native::ocsf::get_src_ip": {
        "description": "Extract the source IP address from the alert (from network_info or OCSF evidences).",
        "module": "analysi.services.cy_ocsf_helpers",
        "class_name": "CyOCSFHelpers",
        "method_name": "get_src_ip",
        "return_type": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
    "native::ocsf::get_dst_ip": {
        "description": "Extract the destination IP address from the alert.",
        "module": "analysi.services.cy_ocsf_helpers",
        "class_name": "CyOCSFHelpers",
        "method_name": "get_dst_ip",
        "return_type": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
    "native::ocsf::get_dst_domain": {
        "description": "Extract the destination domain from the alert (from evidences[].dst_endpoint.domain).",
        "module": "analysi.services.cy_ocsf_helpers",
        "class_name": "CyOCSFHelpers",
        "method_name": "get_dst_domain",
        "return_type": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
    "native::ocsf::get_http_method": {
        "description": "Extract the HTTP method from the alert (from evidences[].http_request.http_method).",
        "module": "analysi.services.cy_ocsf_helpers",
        "class_name": "CyOCSFHelpers",
        "method_name": "get_http_method",
        "return_type": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
    "native::ocsf::get_user_agent": {
        "description": "Extract the user agent string from the alert (from evidences[].http_request.user_agent).",
        "module": "analysi.services.cy_ocsf_helpers",
        "class_name": "CyOCSFHelpers",
        "method_name": "get_user_agent",
        "return_type": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
    "native::ocsf::get_http_response_code": {
        "description": "Extract the HTTP response status code from the alert (from evidences[].http_response.code).",
        "module": "analysi.services.cy_ocsf_helpers",
        "class_name": "CyOCSFHelpers",
        "method_name": "get_http_response_code",
        "return_type": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
    },
    "native::ocsf::get_url": {
        "description": "Extract the URL from the alert (from web_info or OCSF evidences).",
        "module": "analysi.services.cy_ocsf_helpers",
        "class_name": "CyOCSFHelpers",
        "method_name": "get_url",
        "return_type": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
    "native::ocsf::get_url_path": {
        "description": "Extract the URL path from the alert.",
        "module": "analysi.services.cy_ocsf_helpers",
        "class_name": "CyOCSFHelpers",
        "method_name": "get_url_path",
        "return_type": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
    "native::ocsf::get_cve_ids": {
        "description": "Extract all CVE IDs from the alert as a list of strings.",
        "module": "analysi.services.cy_ocsf_helpers",
        "class_name": "CyOCSFHelpers",
        "method_name": "get_cve_ids",
        "return_type": {"type": "array", "items": {"type": "string"}},
    },
    "native::ocsf::get_label": {
        "description": "Get a label value from the alert (e.g., get_label(alert, 'source_category') returns 'Firewall').",
        "module": "analysi.services.cy_ocsf_helpers",
        "class_name": "CyOCSFHelpers",
        "method_name": "get_label",
        "return_type": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
    # ── Project Symi: Alert Ingestion & Checkpoint Functions ──────────
    "native::ingest::ingest_alerts": {
        "description": "Persist OCSF-formatted alerts and emit control events. Returns counts of created, duplicate, and errored alerts.",
        "module": "analysi.services.cy_ingest_functions",
        "class_name": "CyIngestFunctions",
        "method_name": "ingest_alerts",
        "return_type": {
            "type": "object",
            "properties": {
                "created": {"type": "number"},
                "duplicates": {"type": "number"},
                "errors": {"type": "number"},
            },
            "description": "Ingestion summary with created, duplicates, and errors counts",
        },
    },
    "native::ingest::get_checkpoint": {
        "description": "Read a checkpoint value scoped to (tenant, task, key). Returns None if no checkpoint exists.",
        "module": "analysi.services.cy_ingest_functions",
        "class_name": "CyIngestFunctions",
        "method_name": "get_checkpoint",
        "return_type": {
            "anyOf": [
                {"type": "object"},
                {"type": "string"},
                {"type": "number"},
                {"type": "null"},
            ]
        },
    },
    "native::ingest::set_checkpoint": {
        "description": "Write a checkpoint value scoped to (tenant, task, key). Uses UPSERT semantics.",
        "module": "analysi.services.cy_ingest_functions",
        "class_name": "CyIngestFunctions",
        "method_name": "set_checkpoint",
        "return_type": {"type": "null", "description": "No return value"},
    },
    "native::ingest::default_lookback": {
        "description": "Return a configurable lookback time (default: now - 2 hours). Reads ANALYSI_DEFAULT_LOOKBACK_HOURS env var.",
        "module": "analysi.services.cy_ingest_functions",
        "class_name": "CyIngestFunctions",
        "method_name": "default_lookback",
        "return_type": {
            "type": "string",
            "format": "date-time",
            "description": "UTC datetime as ISO 8601 string",
        },
    },
}


def _python_type_to_json_schema(python_type: Any) -> dict[str, Any]:
    """
    Convert Python type annotation to JSON Schema type.

    Args:
        python_type: Python type from type hint (str, int, dict, etc.)

    Returns:
        JSON Schema type dict (e.g., {"type": "string"})
    """
    # Handle None type
    if python_type is type(None):
        return {"type": "null"}

    # Handle basic types
    if python_type is str:
        return {"type": "string"}
    if python_type is int:
        return {"type": "number"}  # Cy language uses "number" for both int and float
    if python_type is float:
        return {"type": "number"}
    if python_type is bool:
        return {"type": "boolean"}
    if python_type is dict:
        return {"type": "object"}
    if python_type is list:
        return {"type": "array"}
    if python_type is bytes:
        return {"type": "string", "format": "binary"}

    # Handle typing module types (Union, Optional, etc.)
    origin = get_origin(python_type)
    args = get_args(python_type)

    if origin is dict:
        # dict[str, Any] -> {"type": "object"}
        return {"type": "object", "additionalProperties": True}
    if origin is list:
        # list[dict] -> {"type": "array", "items": {"type": "object"}}
        if args:
            return {"type": "array", "items": _python_type_to_json_schema(args[0])}
        return {"type": "array"}
    if origin is type(int | str):  # Union type (Python 3.10+)
        # Union[str, None] -> {"type": "string"}  (nullable handled separately)
        # Union[str, bytes, dict] -> {"anyOf": [...]}
        non_none_types = [arg for arg in args if arg is not type(None)]
        if len(non_none_types) == 1:
            return _python_type_to_json_schema(non_none_types[0])
        return {"anyOf": [_python_type_to_json_schema(arg) for arg in non_none_types]}

    # Fallback for unknown types
    return {"type": "object"}


def extract_function_signature(
    module_name: str, class_name: str, method_name: str
) -> dict[str, Any]:
    """
    Extract function signature from a native function method.

    Uses Python's inspect module to extract parameter names, types, and defaults.

    Args:
        module_name: Module path (e.g., "analysi.services.cy_llm_functions")
        class_name: Class name (e.g., "CyLLMFunctions")
        method_name: Method name (e.g., "llm_run")

    Returns:
        Dict with "parameters" and "required" keys:
        {
            "parameters": {"prompt": {"type": "string"}, ...},
            "required": ["prompt"]
        }
    """
    # Import module and get class
    module = importlib.import_module(module_name)
    cls = getattr(module, class_name)

    # Get method
    method = getattr(cls, method_name)

    # Get signature
    sig = inspect.signature(method)

    parameters = {}
    required = []

    for param_name, param in sig.parameters.items():
        # Skip 'self' parameter
        if param_name == "self":
            continue

        # Get type annotation
        if param.annotation != inspect.Parameter.empty:
            param_type = param.annotation
            param_schema = _python_type_to_json_schema(param_type)

            # Add description placeholder (can be enhanced later)
            param_schema["description"] = f"{param_name} parameter"

            parameters[param_name] = param_schema
        else:
            # No type annotation - default to object
            parameters[param_name] = {
                "type": "object",
                "description": f"{param_name} parameter",
            }

        # Check if required (no default value and not Optional)
        if param.default == inspect.Parameter.empty:
            # Check if type is Optional (Union[X, None])
            origin = get_origin(param.annotation)
            args = get_args(param.annotation)

            # Python 3.10+ Union[X, None] is represented as X | None
            is_optional = (
                origin is type(int | str) and type(None) in args
            )  # Union with None

            if not is_optional:
                required.append(param_name)

    return {"parameters": parameters, "required": required}


def generate_native_tool_entry(fqn: str) -> dict[str, Any]:
    """
    Generate complete tool registry entry for a native function.

    Combines:
    - Signature extraction (parameters, required)
    - Manual metadata (description, return_type)
    - Parameter overrides (for cases where auto-extraction isn't sufficient)

    Args:
        fqn: Fully qualified name (e.g., "native::llm::llm_run")

    Returns:
        Complete tool registry entry with description, parameters, required, return_type
    """
    if fqn not in NATIVE_TOOL_METADATA:
        raise ValueError(f"Native function '{fqn}' not found in NATIVE_TOOL_METADATA")

    metadata = NATIVE_TOOL_METADATA[fqn]

    # If metadata provides full "parameters" dict, use it directly (for aliases
    # like table_read_via_id that share a method but have different call signatures).
    if "parameters" in metadata:
        parameters = metadata["parameters"]
        required = list(parameters.keys())  # All explicit params are required
    else:
        # Extract signature from the actual method
        signature = extract_function_signature(
            metadata["module"], metadata["class_name"], metadata["method_name"]
        )

        # Apply parameter overrides if provided
        parameters = signature["parameters"].copy()
        if "parameter_overrides" in metadata:
            for param_name, param_schema in metadata["parameter_overrides"].items():
                parameters[param_name] = param_schema
        required = signature["required"]

    # Build complete entry
    entry = {
        "description": metadata["description"],
        "parameters": parameters,
        "required": required,
        "return_type": metadata["return_type"],
    }

    # Special handling for alert_read - load AlertResponse schema dynamically
    if fqn == "native::alert::alert_read" and entry["return_type"] is None:
        from analysi.schemas.alert import AlertResponse

        entry["return_type"] = AlertResponse.model_json_schema()

    return entry


def get_native_tools_registry() -> dict[str, dict[str, Any]]:
    """
    Get complete native tools registry for all native functions.

    This replaces the manual hardcoded entries in cy_tool_registry.py.

    Returns:
        Dict mapping FQNs to complete tool registry entries:
        {
            "native::llm::llm_run": {
                "description": "...",
                "parameters": {...},
                "required": [...],
                "return_type": {...}
            },
            ...
        }
    """
    registry = {}

    for fqn in NATIVE_TOOL_METADATA:
        registry[fqn] = generate_native_tool_entry(fqn)

    return registry
