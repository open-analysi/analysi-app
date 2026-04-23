"""
Task Execution Engine

Core execution engine for Cy scripts with async processing.
"""

import asyncio
import contextlib
import json
import os
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import UUID

from analysi.config.logging import get_logger
from analysi.constants import ManagedResourceKey, TaskConstants

if TYPE_CHECKING:
    from analysi.schemas.task_execution import TaskExecutionResult

# Import real Cy interpreter
from cy_language import Cy, ExecutionPaused
from sqlalchemy.ext.asyncio import AsyncSession

# Import TaskRun model for type annotations
from analysi.models.task_run import TaskRun

logger = get_logger(__name__)


class TaskExecutor(ABC):
    """Abstract base class for task executors."""

    @abstractmethod
    async def execute(
        self,
        cy_script: str,
        input_data: dict[str, Any],
        execution_context: dict[str, Any] = None,
    ) -> dict[str, Any]:
        """Execute a Cy script with input data dict and execution context."""
        pass


class DefaultTaskExecutor(TaskExecutor):
    """Default task executor for sequential Cy script execution."""

    def __del__(self):
        """Ensure cleanup happens even if not called explicitly."""
        if (
            hasattr(self, "_artifact_session_context")
            and self._artifact_session_context
        ):
            # Can't use await in __del__, so just clear references
            self._artifact_session_context = None
            self._artifact_session = None
            self._cy_functions_instance = None

    async def execute(  # noqa: C901
        self,
        cy_script: str,
        input_data: dict[str, Any],
        execution_context: dict[str, Any] = None,
    ) -> dict[str, Any]:
        """
        Execute a Cy script and return results.

        Args:
            cy_script: The Cy script to execute
            input_data: Input data as dict for the script
            execution_context: Execution context with task/workflow information

        Returns:
            Dict with status, output, and error information
        """
        try:
            # Ensure we start with a clean state
            await self._cleanup_artifact_session()

            # Load tools for Cy interpreter
            tools = self._load_tools(execution_context or {})

            # Add time utility functions (stateless, no context needed)
            time_tools = self._load_time_functions()
            tools.update(time_tools)

            # Add sleep utility (stateless, for testing job lifecycle)
            sleep_tools = self._load_sleep_functions()
            tools.update(sleep_tools)

            # Add artifact functions separately (async operation)
            if execution_context:
                artifact_tools = await self._load_artifact_functions(execution_context)
                tools.update(artifact_tools)

                # Add LLM functions that override cy-language defaults
                llm_tools = await self._load_llm_functions(execution_context)
                tools.update(llm_tools)  # This overrides the default llm_run etc.

                # Add KU functions for table/document access
                ku_tools = await self._load_ku_functions(execution_context)
                tools.update(ku_tools)

                # Add index functions for semantic search
                index_tools = await self._load_index_functions(execution_context)
                tools.update(index_tools)

                # Note: Splunk functions (spl_run, generate_triggering_events_spl) are now
                # available as Naxos integration tools via call_action() - no longer injected

                # Add task composition functions
                task_composition_tools = await self._load_task_functions(
                    execution_context
                )
                tools.update(task_composition_tools)

                # Add Alert functions for alert data access
                tenant_id = execution_context.get("tenant_id")
                if tenant_id:
                    alert_tools = self._load_alert_functions(
                        tenant_id, execution_context
                    )
                    tools.update(alert_tools)

                # Add Enrichment functions for easy alert enrichment
                enrichment_tools = self._load_enrichment_functions(execution_context)
                tools.update(enrichment_tools)

                # Add OCSF alert navigation helpers
                ocsf_helper_tools = self._load_ocsf_helper_functions()
                tools.update(ocsf_helper_tools)

                # Add framework app tools
                app_tools = await self._load_app_tools(execution_context)
                tools.update(app_tools)

                # Add ingest + checkpoint functions
                ingest_tools = await self._load_ingest_functions(execution_context)
                tools.update(ingest_tools)

            mcp_servers = self._configure_mcp_servers()

            # Cy 0.19.0+: Pass all tools directly (FQNs containing :: are preserved)
            # No need to separate app tools - export_custom_tools() handles FQN preservation
            # Cy 0.38+: use run_native_async() to get raw Python objects directly.
            # This avoids the JSON serialization round-trip (run_async → json.loads).
            captured_logs: list[str | dict] = []

            # Bug #30 fix: Extract HITL checkpoint for memoized replay on resume.
            # resume_paused_task stores the checkpoint (with injected answer) in
            # execution_context["_hitl_checkpoint"]. Pass it to run_native_async
            # so the Cy interpreter replays cached nodes and injects the answer.
            checkpoint = None
            checkpoint_data = (execution_context or {}).get("_hitl_checkpoint")
            if checkpoint_data:
                from cy_language import ExecutionCheckpoint

                checkpoint = ExecutionCheckpoint.from_dict(checkpoint_data)

            try:
                interpreter = await Cy.create_async(
                    tools=tools, mcp_servers=mcp_servers, captured_logs=captured_logs
                )
                result = await interpreter.run_native_async(
                    cy_script, input_data, checkpoint=checkpoint
                )
            except AttributeError as e:
                if "create_async" in str(e) or "run_native_async" in str(e):
                    # Fallback: sync API for older versions
                    interpreter = Cy(tools=tools, mcp_servers=mcp_servers)
                    result = interpreter.run_native(cy_script, input_data)
                else:
                    raise

            # Artifacts are now created immediately via REST API - no pending processing needed

            # Handle session cleanup based on whether we reused or created the session
            if hasattr(self, "_reused_session") and self._reused_session:
                # For reused sessions, just commit - don't close or cleanup
                try:
                    if hasattr(self, "_artifact_session") and self._artifact_session:
                        await self._artifact_session.commit()
                    # Clear references but don't close the reused session
                    self._artifact_session = None
                    self._cy_functions_instance = None
                    self._reused_session = None
                except Exception:
                    pass  # Ignore errors with reused sessions
            else:
                # For our own sessions, do full cleanup
                if (
                    hasattr(self, "_artifact_session_context")
                    and self._artifact_session_context
                ):
                    try:
                        if (
                            hasattr(self, "_artifact_session")
                            and self._artifact_session
                        ):
                            await self._artifact_session.commit()
                            await self._artifact_session.close()

                        # Exit context immediately while we still have control
                        await self._artifact_session_context.__aexit__(None, None, None)
                        self._artifact_session_context = None
                        self._artifact_session = None
                    except Exception:
                        # Force cleanup on any error
                        await self._cleanup_artifact_session()

            # Cy 0.38+: run_native_async() returns native Python objects directly.
            # No string parsing needed — result is already a dict, list, int, etc.
            parsed_output = result

            # Check if Cy script returned an error object instead of raising exception
            # This happens when Cy scripts have runtime errors (KeyError, etc.)
            # Only treat it as an error if it's a Cy error format (dict with ONLY "error" key)
            # Don't treat valid structured outputs that include error info (like {"success": False, "error": "..."}) as failures
            if isinstance(parsed_output, dict) and "error" in parsed_output:
                # Cy error format: dict with only "error" key (and maybe "output" which would be None)
                # Valid output with error info: dict with multiple keys like {"success": ..., "error": ..., "message": ...}
                keys = set(parsed_output.keys())
                is_cy_error = keys == {"error"} or (
                    keys == {"error", "output"} and parsed_output.get("output") is None
                )

                if is_cy_error:
                    error_message = parsed_output.get(
                        "error", "Unknown Cy script error"
                    )
                    logger.error(
                        "cy_script_produced_error_output", error_message=error_message
                    )
                    return {
                        "status": "failed",
                        "error": error_message,
                        "output": None,
                        "execution_time": 0.1,
                        "logs": captured_logs,
                    }

            return {
                "status": "completed",
                "output": parsed_output,
                "execution_time": 0.1,
                "logs": captured_logs,
            }

        except ExecutionPaused as ep:
            # HITL: hi-latency tool reached, pause execution
            await self._cleanup_artifact_session()
            return {
                "status": "paused",
                "_hitl_checkpoint": ep.checkpoint.to_dict(),
                "logs": locals().get("captured_logs", []),
            }

        except Exception as e:
            # Clean up artifact session on error - handle reused vs own sessions
            try:
                if hasattr(self, "_reused_session") and self._reused_session:
                    # For reused sessions, just rollback - don't close
                    if hasattr(self, "_artifact_session") and self._artifact_session:
                        await self._artifact_session.rollback()
                    # Clear references but don't close the reused session
                    self._artifact_session = None
                    self._cy_functions_instance = None
                    self._reused_session = None
                else:
                    # For our own sessions, do full cleanup
                    if hasattr(self, "_artifact_session") and self._artifact_session:
                        await self._artifact_session.rollback()
                        await self._artifact_session.close()
                    if (
                        hasattr(self, "_artifact_session_context")
                        and self._artifact_session_context
                    ):
                        await self._artifact_session_context.__aexit__(
                            type(e), e, e.__traceback__
                        )
                        self._artifact_session_context = None
                        self._artifact_session = None
            except Exception:
                # If cleanup fails, just clear references
                self._artifact_session_context = None
                self._artifact_session = None
                self._reused_session = None

            return {
                "status": "failed",
                "error": str(e),
                "output": None,
                "execution_time": 0.1,
                "logs": locals().get("captured_logs", []),
            }

    def _load_tools(self, execution_context: dict[str, Any] = None) -> dict[str, Any]:
        """Load tools for Cy interpreter (base tools only - artifact tools loaded separately).

        Loads native functions from cy-language 0.12.1+:
        - Native functions: len, sum, str, log, from_json, to_json, uppercase, lowercase, join
        - Auto-registered via: import cy_language.native_functions

        Note: LLM functions are loaded separately via _load_llm_functions() in execute()
        Note: Artifact functions are loaded separately in execute() due to async requirements

        Args:
            execution_context: Execution context (unused in base implementation for backward compatibility)

        Returns:
            Dictionary of tool functions for Cy interpreter
        """
        try:
            # Import to register native functions with default_registry
            import cy_language.native_functions  # noqa: F401

            # Load all registered tools from default registry
            from cy_language.ui.tools import default_registry

            tools = default_registry.get_tools_dict()

            return tools

        except ImportError:
            # If cy_language is not available, return empty tools dict
            # This allows the code to run without cy_language dependency
            return {}

    async def _load_llm_functions(
        self, execution_context: dict[str, Any]
    ) -> dict[str, Any]:
        """Load LLM functions that route through the Naxos integration framework.

        These override the default cy-language LLM functions. All LLM calls go
        through IntegrationService.execute_action → framework actions
        (anthropic_agent, openai, gemini). No LangChain on the hot path.

        Args:
            execution_context: Execution context with task/workflow information

        Returns:
            Dictionary of LLM function callables
        """
        try:
            from analysi.repositories.credential_repository import (
                CredentialRepository,
            )
            from analysi.repositories.integration_repository import (
                IntegrationRepository,
            )
            from analysi.services.cy_llm_functions import create_cy_llm_functions
            from analysi.services.integration_service import IntegrationService

            # Get session from execution context (reuse the same session as KU functions)
            session = execution_context.get("session")
            if not session:
                logger.warning(
                    "No session in execution context - LLM functions will use environment fallback"
                )
                return {}

            # Validate session is still active
            if hasattr(session, "is_active") and not session.is_active:
                logger.warning(
                    "Session in execution context is not active - LLM functions will use environment fallback"
                )
                return {}

            # Create integration service (reuses session for DB + credential access)
            integration_repo = IntegrationRepository(session)
            credential_repo = CredentialRepository(session)
            integration_service = IntegrationService(
                integration_repo=integration_repo,
                credential_repo=credential_repo,
            )

            # Create LLM functions — unpack (dict, instance) tuple
            llm_functions, cy_llm_instance = create_cy_llm_functions(
                integration_service, execution_context
            )

            # Store instance so execute() can retrieve accumulated usage after Cy runs
            self._cy_llm_instance = cy_llm_instance

            logger.info("llm_functions_loaded", functions=list(llm_functions.keys()))
            return llm_functions
        except Exception as e:
            logger.warning(
                "failed_to_load_integrationbased_llm_functions", error=str(e)
            )
            logger.warning("Falling back to environment-based LLM functions")
            self._cy_llm_instance = None  # No instance when fallback
            return {}  # Fall back to default cy-language functions

    async def _load_artifact_functions(
        self, execution_context: dict[str, Any]
    ) -> dict[str, Any]:
        """Load artifact functions with execution context.

        Note: Echo EDR functions are now available via Naxos integration framework
        as app::echo_edr::* tools, loaded via _load_app_tools().

        Args:
            execution_context: Execution context with task/workflow information

        Returns:
            Dictionary of artifact function callables
        """
        session_context = None
        try:
            from analysi.services.artifact_service import ArtifactService
            from analysi.services.cy_functions import create_cy_artifact_functions

            # Clean up any existing artifact session first
            await self._cleanup_artifact_session()

            # Check for test session (set via fixture in tests)
            provided_session = getattr(self, "_test_session", None)

            if provided_session and hasattr(provided_session, "bind"):
                # Use the provided test session (test environment)
                artifact_service = ArtifactService(provided_session)
                self._artifact_session = provided_session
                self._artifact_session_context = None
                self._reused_session = True
            else:
                # Create a minimal, isolated session for artifact operations
                from analysi.db.session import AsyncSessionLocal

                # Use a simpler approach: create session but commit immediately after each operation
                session_context = AsyncSessionLocal()
                actual_session = await session_context.__aenter__()
                logger.debug("artifact_session_created", session_id=id(actual_session))
                artifact_service = ArtifactService(actual_session)

                self._artifact_session_context = session_context
                self._artifact_session = actual_session
                self._reused_session = False

            # Create the cy functions (no longer need to store instance for deferred processing)
            functions_dict = create_cy_artifact_functions(
                artifact_service, execution_context
            )

            # Note: Echo EDR functions now available via Naxos integration framework
            # as app::echo_edr::pull_processes, app::echo_edr::pull_browser_history, etc.
            # No need for separate cy_echo_functions - they're loaded via _load_app_tools()

            return functions_dict

        except ImportError:
            # If artifact dependencies are not available, return empty dict
            return {}
        except Exception as e:
            # If session creation fails, clean up and re-raise
            logger.error("failed_to_create_artifact_session", error=str(e))
            if session_context:
                with contextlib.suppress(Exception):
                    await session_context.__aexit__(None, None, None)
            raise

    async def _load_ku_functions(
        self, execution_context: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Load Knowledge Unit access functions for Cy scripts.

        Args:
            execution_context: Execution context with tenant_id

        Returns:
            Dictionary of KU function callables
        """
        # Get tenant_id from context
        tenant_id = execution_context.get("tenant_id")
        if not tenant_id:
            logger.warning(
                "No tenant_id in execution context - KU functions unavailable"
            )
            return {}

        try:
            # Import the KU functions module
            from analysi.services.cy_ku_functions import create_cy_ku_functions

            # Get session from context (should be injected by execute_single_task)
            session = execution_context.get("session")
            if not session:
                logger.warning(
                    "No session in execution context - KU functions unavailable"
                )
                return {}

            # Create and return KU functions
            ku_functions = create_cy_ku_functions(session, tenant_id, execution_context)
            logger.debug("loaded_ku_functions_for_tenant", tenant_id=tenant_id)
            return ku_functions

        except Exception as e:
            logger.error("failed_to_load_ku_functions", error=str(e))
            return {}

    async def _load_index_functions(
        self, execution_context: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Load Knowledge Index functions for Cy scripts.

        Provides index_add, index_search, index_delete for semantic search.
        Constructs its own IntegrationService from the session (same pattern
        as _load_llm_functions).

        Args:
            execution_context: Execution context with tenant_id and session

        Returns:
            Dictionary of index function callables
        """
        tenant_id = execution_context.get("tenant_id")
        if not tenant_id:
            logger.warning(
                "No tenant_id in execution context - Index functions unavailable"
            )
            return {}

        try:
            from analysi.repositories.credential_repository import (
                CredentialRepository,
            )
            from analysi.repositories.integration_repository import (
                IntegrationRepository,
            )
            from analysi.services.cy_index_functions import (
                create_cy_index_functions,
            )
            from analysi.services.integration_service import IntegrationService

            session = execution_context.get("session")
            if not session:
                logger.warning(
                    "No session in execution context - Index functions unavailable"
                )
                return {}

            # Construct IntegrationService from session (same as _load_llm_functions)
            integration_repo = IntegrationRepository(session)
            credential_repo = CredentialRepository(session)
            integration_service = IntegrationService(
                integration_repo=integration_repo,
                credential_repo=credential_repo,
            )

            index_functions = create_cy_index_functions(
                session, tenant_id, execution_context, integration_service
            )
            logger.debug("loaded_index_functions_for_tenant", tenant_id=tenant_id)
            return index_functions

        except Exception as e:
            logger.error("failed_to_load_index_functions", error=str(e))
            return {}

    def _load_alert_functions(
        self, tenant_id: str, execution_context: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Load alert access functions for Cy scripts.

        Args:
            tenant_id: Tenant identifier
            execution_context: Task execution context

        Returns:
            Dictionary of alert functions
        """
        try:
            # Import the alert functions module
            from analysi.services.cy_alert_functions import create_cy_alert_functions

            # Get session from context (should be injected by execute_single_task)
            session = execution_context.get("session")
            if not session:
                logger.warning(
                    "No session in execution context - Alert functions unavailable"
                )
                return {}

            # Create and return alert functions
            alert_functions = create_cy_alert_functions(
                session, tenant_id, execution_context
            )
            logger.debug("loaded_alert_functions_for_tenant", tenant_id=tenant_id)
            return alert_functions

        except Exception as e:
            logger.error("failed_to_load_alert_functions", error=str(e))
            return {}

    def _load_enrichment_functions(
        self,
        execution_context: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Load alert enrichment functions for Cy scripts.

        Provides enrich_alert() function that simplifies adding enrichment data
        to alerts under the task's cy_name key.

        Args:
            execution_context: Task execution context (must contain cy_name)

        Returns:
            Dictionary of enrichment functions
        """
        try:
            from analysi.services.cy_enrichment_functions import (
                create_cy_enrichment_functions,
            )

            enrichment_functions = create_cy_enrichment_functions(execution_context)
            logger.debug("Loaded enrichment functions")
            return enrichment_functions

        except Exception as e:
            logger.error("failed_to_load_enrichment_functions", error=str(e))
            return {}

    def _load_ocsf_helper_functions(self) -> dict[str, Any]:
        """Load OCSF alert navigation helpers for Cy scripts.

        These helpers abstract OCSF's nested structure so Cy
        scripts can call get_primary_user(alert) instead of navigating
        alert["actor"]["user"]["name"]. They work with OCSF
        alert shapes during the dual-write transition.
        """
        try:
            from analysi.services.cy_ocsf_helpers import create_cy_ocsf_helpers

            ocsf_helpers = create_cy_ocsf_helpers()
            logger.debug("Loaded OCSF helper functions", count=len(ocsf_helpers))
            return ocsf_helpers

        except Exception as e:
            logger.error("failed_to_load_ocsf_helper_functions", error=str(e))
            return {}

    async def _load_task_functions(
        self, execution_context: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Load task composition functions for Cy scripts.

        Args:
            execution_context: Full execution context (must be propagated)

        Returns:
            Dictionary of task functions for Cy interpreter
        """
        tenant_id = execution_context.get("tenant_id")
        if not tenant_id:
            logger.warning(
                "No tenant_id in execution context - Task functions unavailable"
            )
            return {}

        try:
            from analysi.services.cy_task_functions import create_cy_task_functions

            session = execution_context.get("session")
            if not session:
                logger.warning(
                    "No session in execution context - Task functions unavailable"
                )
                return {}

            # Create and return task functions
            task_functions = create_cy_task_functions(
                session, tenant_id, execution_context
            )
            logger.debug("loaded_task_functions_for_tenant", tenant_id=tenant_id)
            return task_functions

        except Exception as e:
            logger.error("failed_to_load_task_functions", error=str(e))
            return {}

    async def _load_ingest_functions(
        self, execution_context: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Load ingest + checkpoint functions for Cy scripts.

        Provides get_checkpoint, set_checkpoint, default_lookback (always),
        and ingest_alerts (only when integration_id is present in context).

        Args:
            execution_context: Execution context with tenant_id, task_id, session

        Returns:
            Dictionary of ingest/checkpoint function callables
        """
        tenant_id = execution_context.get("tenant_id")
        if not tenant_id:
            logger.warning(
                "No tenant_id in execution context - Ingest functions unavailable"
            )
            return {}

        try:
            from analysi.services.cy_ingest_functions import (
                create_cy_ingest_functions,
            )

            session = execution_context.get("session")
            if not session:
                logger.warning(
                    "No session in execution context - Ingest functions unavailable"
                )
                return {}

            ingest_functions = create_cy_ingest_functions(
                session, tenant_id, execution_context
            )
            logger.debug(
                "loaded_ingest_functions",
                tenant_id=tenant_id,
                functions=list(ingest_functions.keys()),
            )
            return ingest_functions

        except Exception as e:
            logger.error("failed_to_load_ingest_functions", error=str(e))
            return {}

    def _load_time_functions(self) -> dict[str, Any]:
        """
        Load time utility functions for Cy scripts.

        Returns:
            Dictionary of time functions for Cy interpreter
        """
        try:
            from analysi.services.cy_time_functions import CyTimeFunctions

            time_funcs = CyTimeFunctions()
            # Register with both short name and FQN for compatibility
            tools = {
                "format_timestamp": time_funcs.format_timestamp,
                "native::tools::format_timestamp": time_funcs.format_timestamp,
            }
            return tools
        except Exception as e:
            logger.error("failed_to_load_time_functions", error=str(e))
            return {}

    def _load_sleep_functions(self) -> dict[str, Any]:
        """Load sleep utility function for Cy scripts.

        Returns:
            Dictionary of sleep functions for Cy interpreter.
        """
        try:
            from analysi.services.cy_sleep_functions import CySleepFunctions

            sleep_funcs = CySleepFunctions()
            return {
                "sleep": sleep_funcs.sleep,
                "native::tools::sleep": sleep_funcs.sleep,
            }
        except Exception as e:
            logger.error("failed_to_load_sleep_functions", error=str(e))
            return {}

    async def _load_app_tools(  # noqa: C901
        self, execution_context: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Load Naxos framework integration tools for Cy scripts.

        Queries KU API for all app-type tools and creates wrapper functions
        that execute integration actions via the framework.

        Tools are registered with FQN keys: app::integration_type::action_id
        Cy scripts call them using the same FQN: app::virustotal::ip_reputation(ip="8.8.8.8")

        Args:
            execution_context: Execution context with tenant_id and session

        Returns:
            Dictionary mapping FQN tool names to callable wrappers
        """
        tenant_id = execution_context.get("tenant_id")
        if not tenant_id:
            logger.warning("No tenant_id in execution context - App tools unavailable")
            return {}

        session = execution_context.get("session")
        if not session:
            logger.warning("No session in execution context - App tools unavailable")
            return {}

        try:
            from analysi.repositories.credential_repository import (
                CredentialRepository,
            )
            from analysi.repositories.integration_repository import (
                IntegrationRepository,
            )
            from analysi.services.integration_service import IntegrationService

            # Create repositories and service for action execution
            integration_repo = IntegrationRepository(session)
            credential_repo = CredentialRepository(session)
            integration_service = IntegrationService(
                integration_repo=integration_repo,
                credential_repo=credential_repo,
            )

            # Get integration framework to access manifests (DRY: same as compile time)
            from analysi.integrations.framework.registry import (
                get_registry,
            )

            framework = get_registry()
            manifests = framework.list_integrations()

            # Build tools dictionary with FQN names from manifest
            # Load from framework manifests (same as compile time in load_tool_registry_async)
            # This ensures compile and execute have the same tools available

            # Skip framework tools that collide with native functions.
            # AI integrations (anthropic, openai, gemini) expose llm_run/llm_chat
            # but native::llm::llm_run is the canonical Cy path — loaded separately
            # via _load_llm_functions(). Same logic as cy_tool_registry.py.
            from analysi.services.native_tools_registry import (
                get_native_short_names,
            )

            native_short_names = get_native_short_names()

            tools_dict = {}
            for manifest in manifests:
                # Find tool actions in manifest
                for action_def in manifest.actions:
                    if not action_def.cy_name:
                        continue

                    integration_type = manifest.id
                    action_id = action_def.id

                    # Get short name from manifest (defaults to action_id if not specified)
                    # Framework constructs the full FQN from short name
                    short_name = action_def.cy_name or action_id
                    cy_name = f"app::{integration_type}::{short_name}"

                    # Skip tools that collide with native functions
                    if short_name in native_short_names:
                        logger.debug(
                            "skipping_app_tool_native_collision",
                            cy_name=cy_name,
                            short_name=short_name,
                        )
                        continue

                    # Look up integration instance for this tenant and type
                    # Uses the first enabled integration of this type
                    integrations = await integration_repo.list_integrations(
                        tenant_id, enabled=True, integration_type=integration_type
                    )

                    logger.debug(
                        "integrations_found_for_type",
                        count=len(integrations) if integrations else 0,
                        integration_type=integration_type,
                        tenant_id=tenant_id,
                    )

                    if not integrations:
                        logger.debug(
                            "no_enabled_integration_skipping_tool",
                            integration_type=integration_type,
                            tenant_id=tenant_id,
                            cy_name=cy_name,
                        )
                        continue

                    # Use first enabled integration
                    integration_id = integrations[0].integration_id
                    logger.debug(
                        "using_integration_for_tool",
                        integration_id=integration_id,
                        cy_name=cy_name,
                    )

                    if len(integrations) > 1:
                        logger.debug(
                            "multiple_integrations_found_using_first",
                            integration_type=integration_type,
                            integration_id=integration_id,
                        )

                    # Look up primary credential for this integration
                    primary_credential_id = None
                    try:
                        integration_credentials = (
                            await credential_repo.list_by_integration(
                                tenant_id, integration_id
                            )
                        )
                        # Find the primary credential
                        for ic in integration_credentials:
                            if ic.is_primary:
                                primary_credential_id = ic.credential_id
                                break

                        if not primary_credential_id and integration_credentials:
                            # If no primary, use the first available credential
                            primary_credential_id = integration_credentials[
                                0
                            ].credential_id
                            logger.debug(
                                "no_primary_credential_using_first",
                                integration_id=integration_id,
                            )
                    except Exception as e:
                        logger.warning(
                            "credential_lookup_failed",
                            integration_id=integration_id,
                            error=str(e),
                        )

                    # Create wrapper function for this tool
                    async def create_tool_wrapper(  # noqa: C901
                        int_type: str,
                        act_id: str,
                        act_def: Any,
                        int_id: str,
                        ten_id: str,
                        int_svc: IntegrationService,
                        int_repo: IntegrationRepository,
                        cred_repo: CredentialRepository,
                        cred_id,
                        sess,
                        exec_context: dict[str, Any],
                        tool_cy_name: str,
                    ):
                        """Create closure for tool execution with auto-reload on failure."""
                        # Cache the integration_id and credential_id, but allow refresh on failure
                        cached_int_id = int_id
                        cached_cred_id = cred_id

                        async def tool_wrapper(*args, **kwargs):  # noqa: C901
                            """Execute integration action via framework."""
                            import time

                            nonlocal cached_int_id, cached_cred_id

                            # Record start time for artifact capture
                            start_time = time.time()

                            # Combine positional and keyword arguments
                            # If positional args are provided, map them to parameter names from schema
                            params = kwargs.copy()
                            if (
                                args
                                and act_def.metadata
                                and "params_schema" in act_def.metadata
                            ):
                                schema = act_def.metadata["params_schema"]
                                if "properties" in schema:
                                    param_names = list(schema["properties"].keys())
                                    # Map positional args to parameter names in order
                                    for i, arg in enumerate(args):
                                        if i < len(param_names):
                                            params[param_names[i]] = arg

                            try:
                                logger.debug(
                                    "executing_app_tool",
                                    tenant_id=ten_id,
                                    integration_id=cached_int_id,
                                    integration_type=int_type,
                                    action_id=act_id,
                                    credential_id=cached_cred_id,
                                )
                                result = await int_svc.execute_action(
                                    tenant_id=ten_id,
                                    integration_id=cached_int_id,
                                    integration_type=int_type,
                                    action_id=act_id,
                                    credential_id=cached_cred_id,
                                    params=params,
                                    session=sess,
                                )

                                # Normalize integration results for Cy callers: the author of
                                # `app::integration::action(...)` should get the business payload,
                                # not an envelope with status / timestamp / integration_id / action_id
                                # that they have to project around.
                                if isinstance(result, dict):
                                    # Errors raise — tasks fail cleanly, the workflow decides what to do.
                                    if result.get("status") == "error":
                                        error_msg = result.get("error", "Unknown error")
                                        error_type = result.get(
                                            "error_type", "IntegrationError"
                                        )
                                        raise RuntimeError(f"{error_type}: {error_msg}")

                                    if result.get("status") == "success":
                                        _ENVELOPE_KEYS = {
                                            "status",
                                            "timestamp",
                                            "integration_id",
                                            "action_id",
                                        }
                                        stripped = {
                                            k: v
                                            for k, v in result.items()
                                            if k not in _ENVELOPE_KEYS
                                        }

                                        if "data" in stripped:
                                            payload = stripped.pop("data")
                                            # Merge sibling fields (not_found, summary, message,
                                            # total_objects, ...) INTO the data dict so Cy authors
                                            # see a single flat result. Data keys win on conflict.
                                            # This preserves the success_result(not_found=True,
                                            # data=X) idiom used across the integration framework.
                                            if isinstance(payload, dict) and stripped:
                                                result = {**stripped, **payload}
                                            else:
                                                # data is a list / scalar / already-complete dict;
                                                # return it as-is. Siblings are rare in this case.
                                                result = payload
                                        # Legacy single-field actions (e.g., old Cy functions migrated
                                        # into the framework) return their single payload directly.
                                        elif len(stripped) == 1:
                                            result = next(iter(stripped.values()))
                                        else:
                                            # Flat-style action — return the business fields as-is.
                                            result = stripped if stripped else result

                                # Fire-and-forget artifact capture (don't block on failure)
                                duration_ms = int((time.time() - start_time) * 1000)
                                try:
                                    from analysi.services.artifact_service import (
                                        ArtifactService,
                                    )

                                    artifact_svc = ArtifactService(sess)
                                    await artifact_svc.create_tool_execution_artifact(
                                        tenant_id=ten_id,
                                        tool_fqn=tool_cy_name,
                                        integration_id=cached_int_id,
                                        input_params=params,
                                        output=result,
                                        duration_ms=duration_ms,
                                        analysis_id=(
                                            exec_context.get("analysis_id")
                                            if exec_context
                                            else None
                                        ),
                                        task_run_id=(
                                            exec_context.get("task_run_id")
                                            if exec_context
                                            else None
                                        ),
                                        workflow_run_id=(
                                            exec_context.get("workflow_run_id")
                                            if exec_context
                                            else None
                                        ),
                                        workflow_node_instance_id=(
                                            exec_context.get(
                                                "workflow_node_instance_id"
                                            )
                                            if exec_context
                                            else None
                                        ),
                                    )
                                except Exception as artifact_err:
                                    logger.warning(
                                        "failed_to_create_tool_execution_artifact",
                                        error=str(artifact_err),
                                    )

                                return result
                            except ValueError as e:
                                # If integration not found or credential not found, try to reload from database
                                if "not found for tenant" in str(e) or (
                                    "Credential" in str(e) and "not found" in str(e)
                                ):
                                    if "Credential" in str(e):
                                        logger.warning(
                                            "credential_not_found_reloading",
                                            credential_id=cached_cred_id,
                                            integration_id=cached_int_id,
                                            tenant_id=ten_id,
                                        )
                                    else:
                                        logger.warning(
                                            "integration_not_found_reloading",
                                            integration_id=cached_int_id,
                                            integration_type=int_type,
                                            tenant_id=ten_id,
                                        )
                                    try:
                                        # Reload integration by type
                                        integrations = await int_repo.list_integrations(
                                            ten_id,
                                            enabled=True,
                                            integration_type=int_type,
                                        )
                                        if not integrations:
                                            logger.error(
                                                "no_enabled_integration_after_reload",
                                                integration_type=int_type,
                                            )
                                            return {
                                                "status": "error",
                                                "error": f"No enabled integration of type '{int_type}' found",
                                                "integration_type": int_type,
                                                "action_id": act_id,
                                            }

                                        # Update cached values
                                        cached_int_id = integrations[0].integration_id
                                        logger.info(
                                            "integration_reloaded",
                                            integration_id=cached_int_id,
                                            integration_type=int_type,
                                        )

                                        # Reload credential
                                        integration_credentials = (
                                            await cred_repo.list_by_integration(
                                                ten_id, cached_int_id
                                            )
                                        )
                                        cached_cred_id = None  # Reset credential ID
                                        for ic in integration_credentials:
                                            if ic.is_primary:
                                                cached_cred_id = ic.credential_id
                                                break
                                        if (
                                            not cached_cred_id
                                            and integration_credentials
                                        ):
                                            cached_cred_id = integration_credentials[
                                                0
                                            ].credential_id

                                        if cached_cred_id:
                                            logger.info(
                                                "reloaded_credential_for_integration",
                                                cached_cred_id=cached_cred_id,
                                                cached_int_id=cached_int_id,
                                            )
                                        else:
                                            logger.warning(
                                                "no_credentials_found_for_integration",
                                                cached_int_id=cached_int_id,
                                            )

                                        # Retry with new integration_id and credential_id
                                        logger.info(
                                            "retrying_with_reloaded_integration",
                                            cached_int_id=cached_int_id,
                                        )
                                        result = await int_svc.execute_action(
                                            tenant_id=ten_id,
                                            integration_id=cached_int_id,
                                            integration_type=int_type,
                                            action_id=act_id,
                                            credential_id=cached_cred_id,
                                            params=params,
                                            session=sess,
                                        )

                                        # Apply same backward compatibility logic as above
                                        if isinstance(result, dict):
                                            # Raise exceptions for errors (original Cy function behavior)
                                            if result.get("status") == "error":
                                                error_msg = result.get(
                                                    "error", "Unknown error"
                                                )
                                                error_type = result.get(
                                                    "error_type", "IntegrationError"
                                                )
                                                raise RuntimeError(
                                                    f"{error_type}: {error_msg}"
                                                )

                                            # Unwrap successful results
                                            if result.get("status") == "success":
                                                unwrapped = {
                                                    k: v
                                                    for k, v in result.items()
                                                    if k not in ["status", "timestamp"]
                                                }
                                                if len(unwrapped) == 1:
                                                    result = next(
                                                        iter(unwrapped.values())
                                                    )
                                                else:
                                                    result = (
                                                        unwrapped
                                                        if unwrapped
                                                        else result
                                                    )

                                        # Fire-and-forget artifact capture for retry path
                                        duration_ms = int(
                                            (time.time() - start_time) * 1000
                                        )
                                        try:
                                            from analysi.services.artifact_service import (
                                                ArtifactService,
                                            )

                                            artifact_svc = ArtifactService(sess)
                                            await artifact_svc.create_tool_execution_artifact(
                                                tenant_id=ten_id,
                                                tool_fqn=tool_cy_name,
                                                integration_id=cached_int_id,
                                                input_params=params,
                                                output=result,
                                                duration_ms=duration_ms,
                                                analysis_id=(
                                                    exec_context.get("analysis_id")
                                                    if exec_context
                                                    else None
                                                ),
                                                task_run_id=(
                                                    exec_context.get("task_run_id")
                                                    if exec_context
                                                    else None
                                                ),
                                                workflow_run_id=(
                                                    exec_context.get("workflow_run_id")
                                                    if exec_context
                                                    else None
                                                ),
                                                workflow_node_instance_id=(
                                                    exec_context.get(
                                                        "workflow_node_instance_id"
                                                    )
                                                    if exec_context
                                                    else None
                                                ),
                                            )
                                        except Exception as artifact_err:
                                            logger.warning(
                                                "failed_to_create_tool_execution_artifact_retry",
                                                error=str(artifact_err),
                                            )

                                        return result
                                    except Exception as retry_error:
                                        logger.error(
                                            "retry_after_reload_failed",
                                            error=str(retry_error),
                                        )
                                        return {
                                            "status": "error",
                                            "error": f"Reload and retry failed: {retry_error!s}",
                                            "integration_type": int_type,
                                            "action_id": act_id,
                                        }
                                else:
                                    # Different ValueError, re-raise
                                    raise
                            except RuntimeError:
                                # Re-raise RuntimeError for Cy interpreter to catch
                                # This ensures error propagation from integration actions
                                raise
                            except Exception as e:
                                logger.error(
                                    "app_tool_execution_failed",
                                    integration_type=int_type,
                                    action_id=act_id,
                                    error=str(e),
                                )
                                return {
                                    "status": "error",
                                    "error": str(e),
                                    "integration_type": int_type,
                                    "action_id": act_id,
                                }

                        return tool_wrapper

                    # Create the wrapper
                    wrapper = await create_tool_wrapper(
                        integration_type,
                        action_id,
                        action_def,
                        integration_id,
                        tenant_id,
                        integration_service,
                        integration_repo,
                        credential_repo,
                        primary_credential_id,
                        session,
                        execution_context,  # For artifact linking
                        cy_name,  # Tool FQN for artifact name
                    )

                    # Register with cy_name from manifest (or auto-generated FQN)
                    # Cy 0.11.0 supports app:: namespace - tools must be registered with FQN
                    # HITL: dict-style for hi_latency tools
                    if action_def.metadata.get("hi_latency"):
                        tools_dict[cy_name] = {"fn": wrapper, "hi_latency": True}
                    else:
                        tools_dict[cy_name] = wrapper

                    logger.debug("registered_app_tool", cy_name=cy_name)

            logger.info(
                "loaded_app_tools_for_tenant",
                tools_dict_count=len(tools_dict),
                tenant_id=tenant_id,
            )
            return tools_dict

        except Exception as e:
            logger.error("failed_to_load_app_tools", error=str(e), exc_info=True)
            return {}

    async def _cleanup_artifact_session(self):
        """Clean up any existing artifact session and resources."""
        try:
            import asyncio

            # Check if we have the same event loop
            try:
                current_loop = asyncio.get_running_loop()
                if (
                    hasattr(self, "_session_loop")
                    and self._session_loop != current_loop
                ):
                    # Different event loop, just clear references without async operations
                    self._artifact_session_context = None
                    self._artifact_session = None
                    self._cy_functions_instance = None
                    self._session_loop = None
                    return
            except RuntimeError:
                # No event loop running, just clear references
                self._artifact_session_context = None
                self._artifact_session = None
                self._cy_functions_instance = None
                self._session_loop = None
                return

            if (
                hasattr(self, "_artifact_session_context")
                and self._artifact_session_context
            ):
                # Try to rollback any pending transactions first
                if hasattr(self, "_artifact_session") and self._artifact_session:
                    session_id = id(self._artifact_session)
                    logger.debug(
                        "cleaning_up_artifact_session_rolling_back_transact",
                        session_id=session_id,
                    )
                    try:
                        await self._artifact_session.rollback()
                    except Exception as e:
                        logger.debug(
                            "artifact_session_rollback_failed",
                            session_id=session_id,
                            error=str(e),
                        )

                # Close the session explicitly to release connections
                if hasattr(self, "_artifact_session") and self._artifact_session:
                    session_id = id(self._artifact_session)
                    logger.debug(
                        "artifact_session_closing_session", session_id=session_id
                    )
                    try:
                        await self._artifact_session.close()
                    except Exception as e:
                        logger.debug(
                            "artifact_session_close_failed",
                            session_id=session_id,
                            error=str(e),
                        )

                # Exit the session context
                try:
                    logger.debug("Artifact session: Exiting session context")
                    await self._artifact_session_context.__aexit__(None, None, None)
                    logger.debug("Artifact session: Session context cleanup completed")
                except Exception as e:
                    logger.debug(
                        "artifact_session_context_cleanup_failed", error=str(e)
                    )

                self._artifact_session_context = None
                self._artifact_session = None

            # Clear cy functions instance and loop reference
            if hasattr(self, "_cy_functions_instance"):
                self._cy_functions_instance = None
            if hasattr(self, "_session_loop"):
                self._session_loop = None

            # Clear LLM factory cache to prevent memory leaks
            if hasattr(self, "_llm_factory_cache"):
                self._llm_factory_cache.clear()

        except Exception:
            pass  # Ignore all cleanup errors - we just want to ensure clean state

    def _configure_mcp_servers(self) -> dict[str, dict[str, str]] | None:
        """Configure MCP servers from environment variable.

        Reads MCP_SERVERS environment variable (JSON format).
        Integration tools (VirusTotal, Splunk, etc.) are accessed via app:: namespace,
        not MCP servers. MCP servers only used when explicitly configured.

        Returns:
            MCP server configuration dict or None if not configured
        """
        import os

        # Allow MCP servers in tests if MCP_SERVERS environment variable is explicitly set
        if (
            os.getenv("PYTEST_CURRENT_TEST") is not None
            and os.getenv("MCP_SERVERS") is None
        ):
            return None

        # Try to load from environment variable first
        mcp_servers_env = os.getenv("MCP_SERVERS")
        if mcp_servers_env:
            try:
                mcp_servers = json.loads(mcp_servers_env)
                return mcp_servers
            except json.JSONDecodeError:
                # Fall through to return None if JSON parsing fails
                pass

        # No hardcoded MCP servers - return None
        # Integration tools are accessed via app:: namespace (Naxos framework)
        # MCP servers only used when explicitly configured via MCP_SERVERS env var
        return None


class TaskExecutionService:
    """Service for managing async task execution with thread pools."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue = asyncio.Queue()
        self.executor = DefaultTaskExecutor()  # Public for testing
        config = ExecutorConfigManager.load_from_env()
        self.max_workers = config["threads"]
        self.timeout = config["timeout"]

    async def queue_task(self, task_run: TaskRun) -> None:
        """Queue a task run for execution."""
        await self._queue.put(task_run)

    async def process_queue(self) -> None:
        """Process all queued tasks asynchronously."""
        tasks = []

        # Create worker tasks up to max_workers
        for _ in range(self.max_workers):
            task = asyncio.create_task(self._worker())
            tasks.append(task)

        # Wait for all tasks to complete
        await asyncio.gather(*tasks, return_exceptions=True)

    async def execute_single_task(
        self,
        task_run_id: UUID,
        tenant_id: str,
    ) -> "TaskExecutionResult":
        """Execute a single task run and return the result.

        Creates its own isolated AsyncSession — callers must NOT pass a session.
        DB persistence (updating task_run status/output) is the caller's responsibility.
        Use execute_and_persist() for fire-and-forget callers that want the old behaviour.

        Args:
            task_run_id: ID of the TaskRun to execute.
            tenant_id: Tenant identifier for the task run.

        Returns:
            TaskExecutionResult with status, output_data, error_message,
            execution_time_ms, and task_run_id.
        """
        from analysi.db.session import AsyncSessionLocal

        logger.debug(
            "task_creating_isolated_session_for_execution", task_run_id=task_run_id
        )
        async with AsyncSessionLocal() as session:
            task_run = await self._load_task_run(session, task_run_id, tenant_id)
            result = await self._execute_task_with_session(task_run, session)
            await session.commit()
            logger.debug(
                "task_execution_complete_status",
                task_run_id=task_run_id,
                status=result.status,
            )
            return result

    async def execute_and_persist(
        self,
        task_run_id: UUID,
        tenant_id: str,
    ) -> None:
        """Execute a task and immediately persist the result to the DB.

        Convenience wrapper for fire-and-forget callers (routers, queue worker).
        Preserves the same end-state in the DB as the old execute_single_task() API.

        Args:
            task_run_id: ID of the TaskRun to execute.
            tenant_id: Tenant identifier for the task run.
        """
        from analysi.db.session import AsyncSessionLocal
        from analysi.schemas.task_execution import TaskExecutionStatus
        from analysi.services.task_run import TaskRunService

        result = await self.execute_single_task(task_run_id, tenant_id)

        task_run_service = TaskRunService()
        async with AsyncSessionLocal() as persist_session:
            if result.status == TaskExecutionStatus.PAUSED:
                # HITL: persist paused status.
                # Store a clean status object as output (not the raw checkpoint).
                # The checkpoint is saved separately in execution_context by
                # update_status() so the UI doesn't see the internal blob.
                checkpoint_data = (result.output_data or {}).get("_hitl_checkpoint", {})
                pending_args = checkpoint_data.get("pending_tool_args", {})
                paused_output = {
                    "status": "paused",
                    "reason": "waiting_for_human_response",
                    "question": pending_args.get("question"),
                    "channel": pending_args.get("destination"),
                }
                await task_run_service.update_status(
                    persist_session,
                    result.task_run_id,
                    TaskConstants.Status.PAUSED,
                    output_data={
                        **paused_output,
                        "_hitl_checkpoint": checkpoint_data,
                    },
                    llm_usage=result.llm_usage,
                )
                if checkpoint_data:
                    from analysi.repositories.hitl_repository import (
                        create_question_from_checkpoint,
                    )

                    hitl_question = await create_question_from_checkpoint(
                        session=persist_session,
                        tenant_id=tenant_id,
                        task_run_id=result.task_run_id,
                        checkpoint_data=checkpoint_data,
                    )
                    # R21: send the Slack message and update question_ref
                    if hitl_question is not None:
                        from analysi.slack_listener.sender import (
                            send_hitl_question,
                        )

                        await send_hitl_question(
                            session=persist_session,
                            hitl_question=hitl_question,
                            pending_tool_args=checkpoint_data.get(
                                "pending_tool_args", {}
                            ),
                            tenant_id=tenant_id,
                        )
            elif result.status == TaskExecutionStatus.COMPLETED:
                await task_run_service.update_status(
                    persist_session,
                    result.task_run_id,
                    TaskConstants.Status.COMPLETED,
                    output_data=result.output_data,
                    llm_usage=result.llm_usage,
                )
            else:
                await task_run_service.update_status(
                    persist_session,
                    result.task_run_id,
                    TaskConstants.Status.FAILED,
                    error_info={"error": result.error_message or "Unknown error"},
                    llm_usage=result.llm_usage,
                )
            await persist_session.commit()

        # Update Integration.health_status if this was a health check.
        # Fire-and-forget — failure here must not affect the TaskRun.
        await self._maybe_update_integration_health(
            task_run_id=result.task_run_id,
            tenant_id=tenant_id,
            status=result.status.value
            if hasattr(result.status, "value")
            else str(result.status),
            output_data=result.output_data,
        )

        # Persist log entries as an execution_log artifact (skip if empty).
        # Uses a separate session so a DB error here cannot affect the
        # TaskRun status update committed above.
        if result.log_entries:
            try:
                async with AsyncSessionLocal() as log_session:
                    task_run = await task_run_service.get_task_run(
                        log_session, tenant_id, result.task_run_id
                    )
                    await self._persist_log_artifact(
                        log_session, tenant_id, result, task_run
                    )
            except Exception:
                logger.warning(
                    "log_artifact_persist_failed",
                    task_run_id=str(task_run_id),
                    exc_info=True,
                )

    async def _persist_log_artifact(
        self,
        session: AsyncSession,
        tenant_id: str,
        result: "TaskExecutionResult",
        task_run: TaskRun | None = None,
    ) -> None:
        """Store log_entries from a TaskExecutionResult as an execution_log artifact.

        Creates a JSON artifact containing the log entries list so they can
        be retrieved later via the REST API.

        Args:
            session: Active database session (not yet committed).
            tenant_id: Tenant identifier.
            result: Execution result containing log_entries.
            task_run: Optional TaskRun for workflow/analysis context linkage.
        """
        from analysi.schemas.artifact import ArtifactCreate
        from analysi.services.artifact_service import ArtifactService

        content = json.dumps({"entries": result.log_entries})

        # Extract relationship context from TaskRun (mirrors other auto-capture helpers)
        exec_ctx = (task_run.execution_context or {}) if task_run else {}
        analysis_id_raw = exec_ctx.get("analysis_id")

        artifact_data = ArtifactCreate(
            name="execution_log",
            content=content,
            artifact_type="execution_log",
            mime_type="application/json",
            task_run_id=result.task_run_id,
            workflow_run_id=task_run.workflow_run_id if task_run else None,
            workflow_node_instance_id=(
                task_run.workflow_node_instance_id if task_run else None
            ),
            analysis_id=UUID(analysis_id_raw) if analysis_id_raw else None,
            source="auto_capture",
        )

        artifact_service = ArtifactService(session)
        await artifact_service.create_artifact(tenant_id, artifact_data)

    async def _maybe_update_integration_health(
        self,
        task_run_id: UUID,
        tenant_id: str,
        status: str,
        output_data: Any,
    ) -> None:
        """Update Integration.health_status if this TaskRun belongs to a health check.

        Fire-and-forget: uses its own session so failures here never affect
        the already-committed TaskRun.  Matches the _persist_log_artifact pattern.

        Wires process_health_check_result() to the execution pipeline.
        """
        try:
            from sqlalchemy import select

            from analysi.db.session import AsyncSessionLocal
            from analysi.models.task import Task
            from analysi.models.task_run import TaskRun as TaskRunModel
            from analysi.repositories.integration_repository import (
                IntegrationRepository,
            )
            from analysi.services.task_factory import process_health_check_result

            async with AsyncSessionLocal() as session:
                # Single query: JOIN TaskRun→Task, filter to health checks only.
                # For non-health-check tasks this returns no rows (1 query, fast exit).
                stmt = (
                    select(Task.integration_id)
                    .join(TaskRunModel, TaskRunModel.task_id == Task.component_id)
                    .where(
                        TaskRunModel.id == task_run_id,
                        Task.managed_resource_key == ManagedResourceKey.HEALTH_CHECK,
                        Task.integration_id.isnot(None),
                    )
                )
                row = await session.execute(stmt)
                integration_id = row.scalar_one_or_none()
                if not integration_id:
                    return

                health_status = process_health_check_result(status, output_data)

                repo = IntegrationRepository(session)
                await repo.update_health_status(
                    tenant_id=tenant_id,
                    integration_id=integration_id,
                    health_status=health_status,
                    last_health_check_at=datetime.now(UTC),
                )
                await session.commit()

                logger.info(
                    "integration_health_updated",
                    integration_id=integration_id,
                    health_status=health_status,
                    task_run_id=str(task_run_id),
                )

        except Exception:
            logger.warning(
                "integration_health_update_failed",
                task_run_id=str(task_run_id),
                exc_info=True,
            )

    async def resume_paused_task(
        self,
        session: AsyncSession,
        task_run_id: UUID,
        tenant_id: str,
        human_response: Any,
    ) -> "TaskExecutionResult":
        """Resume a paused task by injecting the human's answer (HITL).

        Loads the checkpoint from execution_context, injects the human_response
        as the pending tool's result, and re-executes the Cy script. Memoized
        replay ensures all prior nodes return instantly from cache.

        Args:
            session: Active AsyncSession.
            task_run_id: ID of the paused TaskRun.
            tenant_id: Tenant identifier.
            human_response: The human's answer to inject.

        Returns:
            TaskExecutionResult from the resumed execution.

        Raises:
            ValueError: If the task_run is not paused or has no checkpoint.
        """
        from cy_language import ExecutionCheckpoint
        from sqlalchemy import select

        # Bug #23 fix: Filter by tenant_id for multi-tenant isolation.
        stmt = select(TaskRun).where(
            TaskRun.id == task_run_id,
            TaskRun.tenant_id == tenant_id,
        )
        result = await session.execute(stmt)
        task_run = result.scalar_one_or_none()

        if task_run is None:
            raise ValueError(f"TaskRun {task_run_id} not found for tenant {tenant_id}")

        if task_run.status != TaskConstants.Status.PAUSED:
            raise ValueError(
                f"TaskRun {task_run_id} is not paused (status={task_run.status})"
            )

        checkpoint_data = (task_run.execution_context or {}).get("_hitl_checkpoint")
        if not checkpoint_data:
            raise ValueError(f"TaskRun {task_run_id} has no checkpoint to resume")

        # Inject the human's answer into the checkpoint
        checkpoint_data["pending_tool_result"] = human_response
        checkpoint = ExecutionCheckpoint.from_dict(checkpoint_data)

        # Store updated checkpoint back (so it persists even if execution fails).
        # Bug #30 fix: Use direct SQL UPDATE instead of ORM attribute assignment.
        # SQLAlchemy JSONB mutation tracking does not reliably detect nested
        # changes even when the top-level dict is replaced. A raw UPDATE
        # bypasses the ORM and guarantees the JSONB column is persisted.
        from sqlalchemy import update

        updated_ctx = dict(task_run.execution_context or {})
        updated_ctx["_hitl_checkpoint"] = checkpoint.to_dict()

        stmt = (
            update(TaskRun)
            .where(TaskRun.id == task_run_id)
            .values(
                execution_context=updated_ctx,
                status=TaskConstants.Status.RUNNING,
            )
        )
        await session.execute(stmt)
        await session.commit()

        # Re-execute via execute_single_task (which creates its own session)
        exec_result = await self.execute_single_task(task_run_id, tenant_id)
        return exec_result

    async def _load_task_run(
        self, session: AsyncSession, task_run_id: UUID, tenant_id: str
    ) -> TaskRun:
        """Load a TaskRun from the DB by ID.

        Args:
            session: Active AsyncSession to query with.
            task_run_id: ID of the TaskRun.
            tenant_id: Tenant identifier (for logging/future filtering).

        Returns:
            The TaskRun ORM object.

        Raises:
            ValueError: If the TaskRun is not found.
        """
        from sqlalchemy import select

        stmt = select(TaskRun).where(TaskRun.id == task_run_id)
        result = await session.execute(stmt)
        task_run = result.scalar_one_or_none()
        if task_run is None:
            raise ValueError(f"TaskRun {task_run_id} not found")
        return task_run

    async def _execute_task_with_session(  # noqa: C901
        self, task_run: TaskRun, session: AsyncSession
    ) -> "TaskExecutionResult":
        """Execute a single task run with a provided session.

        Returns a TaskExecutionResult — does NOT write to the database.
        All DB persistence is the caller's responsibility.
        """
        import time

        from analysi.schemas.task_execution import (
            TaskExecutionResult,
            TaskExecutionStatus,
        )
        from analysi.services.task_run import TaskRunService

        start_ms = int(time.monotonic() * 1000)

        try:
            # Get Cy script from task_run (ad-hoc) or load from task
            cy_script = task_run.cy_script
            if not cy_script and task_run.task_id:
                # Load script from the task
                from analysi.services.task import TaskService

                task_service = TaskService(session)
                task = await task_service.get_task(task_run.task_id, task_run.tenant_id)  # type: ignore
                if task and task.script:
                    cy_script = task.script  # type: ignore

            # Default script if none found
            if not cy_script:
                cy_script = "return 'No script provided'"  # type: ignore

            # Get input data from storage - Cy interpreter expects dict, not JSON string
            task_run_service = TaskRunService()
            input_data = await task_run_service.retrieve_input_data(task_run) or {}

            # Update last_used_at field for the Component when task execution starts
            if task_run.task_id:
                # Get the component_id from the task and update it directly
                await self._update_component_last_used_at_by_task(
                    task_run.task_id, task_run.tenant_id, session
                )  # type: ignore

            # Get the task's app if this is a saved task (not ad-hoc)
            app = "default"
            task = None  # Initialize for ad-hoc tasks
            if task_run.task_id:
                # Query the task directly to get its app
                from sqlalchemy import select

                from analysi.models.component import Component
                from analysi.models.task import Task

                stmt = (
                    select(Task)
                    .join(Component, Task.component_id == Component.id)
                    .where(
                        Task.component_id == task_run.task_id,
                        Component.tenant_id == task_run.tenant_id,
                    )
                )
                result = await session.execute(stmt)
                task = result.scalar_one_or_none()

                if task:
                    # Load the component relationship
                    await session.refresh(task, ["component"])
                    app = task.component.app

            # Build execution context for artifact functions and other tools.
            # SECURITY: Spread user-supplied context FIRST, then overlay trusted
            # fields so they cannot be overridden by stored execution_context
            # (which originates from REST input). Defense-in-depth: task_run.py
            # also strips protected keys at ingestion time.
            cy_name = task.component.cy_name if task else None
            execution_context = {
                # User-supplied fields first (may include analysis_id, alert_id, etc.)
                **(task_run.execution_context or {}),
                # Trusted fields AFTER spread — cannot be overridden
                "task_id": str(task_run.task_id) if task_run.task_id else None,
                "task_run_id": str(task_run.id),
                "tenant_id": task_run.tenant_id,
                "app": app,
                "cy_name": cy_name,
                # Propagate integration_id so Cy functions like ingest_alerts()
                # are available regardless of how the task was triggered.
                **(
                    {"integration_id": task.integration_id}
                    if task and task.integration_id
                    else {}
                ),
                "workflow_run_id": (
                    str(task_run.workflow_run_id) if task_run.workflow_run_id else None
                ),
                "session": session,  # Intentional: nested task_run() calls are subroutines of
                # this task — they share identity (task_run_id), transaction, and artifacts.
                # Removing the session would break task composition. This is correct scoping,
                # not coupling.
                "directive": task.directive if task else None,
            }

            # Load active feedback entries for prompt augmentation
            # Wrapped in a savepoint so a failed query doesn't corrupt the
            # session's transaction (which would cause InFailedSQLTransactionError
            # on subsequent DB operations like the execution_context UPDATE).
            if task_run.task_id:
                try:
                    from analysi.services.feedback_relevance import (
                        FeedbackRelevanceService,
                    )
                    from analysi.services.task_feedback import TaskFeedbackService

                    async with session.begin_nested():
                        feedback_svc = TaskFeedbackService(session)
                        feedback_docs = await feedback_svc.list_active_feedback(
                            task_run.tenant_id,
                            task_run.task_id,  # type: ignore
                        )
                    if feedback_docs:
                        execution_context["feedback_entries"] = [
                            doc.content for doc in feedback_docs if doc.content
                        ]
                        # Create Valkey-backed relevance service for LLM filtering
                        relevance_svc = await FeedbackRelevanceService.create()
                        execution_context["feedback_relevance_service"] = relevance_svc
                        logger.info(
                            "task_feedback_loaded",
                            count=len(feedback_docs),
                            task_id=str(task_run.task_id),
                        )
                except Exception as e:
                    logger.warning("task_feedback_load_failed", error=str(e))

            # Persist cy_name to task_run.execution_context in database
            # This enables the enrichment endpoint to extract task-specific enrichments
            # NOTE: Use direct SQL UPDATE because task_run may be detached from this session
            # (API path creates task_run in request session, executes in background session)
            if cy_name and (
                not task_run.execution_context
                or task_run.execution_context.get("cy_name") != cy_name
            ):
                from sqlalchemy import update

                updated_context = dict(task_run.execution_context or {})
                updated_context["cy_name"] = cy_name

                stmt = (
                    update(TaskRun)
                    .where(TaskRun.id == task_run.id)
                    .values(execution_context=updated_context)
                )
                await session.execute(stmt)
                # Also update local object for use in this execution
                task_run.execution_context = updated_context

            # Pass test session to executor if available (for testing)
            if hasattr(self, "_test_session") and self._test_session:
                self.executor._test_session = self._test_session

            # Execute using the executor with parsed input data and execution context
            raw_result = await self.executor.execute(
                cy_script, input_data, execution_context
            )  # type: ignore

            # Capture CyLLMFunctions instance NOW, before _run_post_hooks()
            # overwrites self.executor._cy_llm_instance with a fresh instance for
            # the post-hook llm_summarize() call.
            cy_llm_instance_for_usage = getattr(self.executor, "_cy_llm_instance", None)

            # Run post-task completion hooks (e.g., auto-generate ai_analysis_title)
            if (
                raw_result.get("status") == "completed"
                and raw_result.get("output")
                and task
            ):
                raw_result = await self._run_post_hooks(
                    result=raw_result,
                    task=task,
                    execution_context=execution_context,
                    original_input=input_data,
                )

            elapsed_ms = int(time.monotonic() * 1000) - start_ms

            # Retrieve accumulated LLM usage (captured before post-hooks ran)
            llm_usage = None
            if cy_llm_instance_for_usage is not None:
                llm_usage = cy_llm_instance_for_usage.get_total_usage()

            # HITL: handle paused status from executor
            if raw_result.get("status") == "paused":
                return TaskExecutionResult(
                    status=TaskExecutionStatus.PAUSED,
                    output_data={
                        "_hitl_checkpoint": raw_result.get("_hitl_checkpoint")
                    },
                    error_message=None,
                    execution_time_ms=elapsed_ms,
                    task_run_id=task_run.id,  # type: ignore
                    log_entries=raw_result.get("logs", []),
                    llm_usage=llm_usage,
                )

            if raw_result.get("status") == "completed":
                # Cy 0.38+: run_native_async() returns native Python objects.
                # No string parsing needed.
                output_data = raw_result.get("output")

                return TaskExecutionResult(
                    status=TaskExecutionStatus.COMPLETED,
                    output_data=output_data,
                    error_message=None,
                    execution_time_ms=elapsed_ms,
                    task_run_id=task_run.id,  # type: ignore
                    log_entries=raw_result.get("logs", []),
                    llm_usage=llm_usage,
                )
            return TaskExecutionResult(
                status=TaskExecutionStatus.FAILED,
                output_data=None,
                error_message=raw_result.get("error", "Unknown error"),
                execution_time_ms=elapsed_ms,
                task_run_id=task_run.id,  # type: ignore
                log_entries=raw_result.get("logs", []),
                llm_usage=llm_usage,
            )

        except Exception as e:
            elapsed_ms = int(time.monotonic() * 1000) - start_ms
            # Best-effort: if executor.execute() ran, we captured the
            # CyLLMFunctions instance before post-hooks.  Retrieve usage even on
            # failure so we don't lose cost data for LLM calls that did happen.
            llm_usage_on_error = None
            try:
                inst = locals().get("cy_llm_instance_for_usage")
                if inst is not None:
                    llm_usage_on_error = inst.get_total_usage()
            except Exception:
                pass
            return TaskExecutionResult(
                status=TaskExecutionStatus.FAILED,
                output_data=None,
                error_message=str(e),
                execution_time_ms=elapsed_ms,
                task_run_id=task_run.id,  # type: ignore
                llm_usage=llm_usage_on_error,
            )

    async def _run_post_hooks(
        self,
        result: dict[str, Any],
        task: Any,
        execution_context: dict[str, Any],
        original_input: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """
        Run post-task completion hooks on the result.

        Hooks can modify the task output (e.g., add ai_analysis_title).

        Args:
            result: The execution result dict with status and output
            task: The Task model object with name, description, directive
            execution_context: Execution context including cy_name
            original_input: The original input data (alert) passed to the task

        Returns:
            Modified result dict after all hooks have run
        """
        try:
            from analysi.services.task_post_hooks import (
                TaskMetadata,
                create_task_post_hooks,
            )

            # Get LLM functions for the hooks
            llm_functions = await self.executor._load_llm_functions(execution_context)
            if not llm_functions:
                logger.debug("No LLM functions available - skipping post-hooks")
                return result

            # Create post-hooks instance
            post_hooks = create_task_post_hooks(llm_functions, execution_context)
            if not post_hooks:
                logger.debug("Post-hooks not created (llm_summarize not available)")
                return result

            # Build task metadata
            # Note: name and description are on Component, directive is on Task
            # Use task.component if loaded and not None, otherwise use fallbacks
            component = getattr(task, "component", None)
            task_metadata = TaskMetadata(
                name=component.name if component else getattr(task, "name", "Unknown"),
                description=component.description if component else None,
                directive=task.directive,
                cy_name=execution_context.get("cy_name"),
            )

            # Run hooks on the output
            modified_output = await post_hooks.run_all_hooks(
                task_output=result.get("output"),
                task_metadata=task_metadata,
                original_input=original_input,
            )

            # Return result with modified output
            result["output"] = modified_output
            return result

        except Exception as e:
            # Don't fail the task if post-hooks fail
            logger.warning("posttask_hooks_failed", error=str(e))
            return result

    def has_queued_tasks(self) -> bool:
        """Check if there are tasks in the queue."""
        return not self._queue.empty()

    def queue_size(self) -> int:
        """Get the current queue size."""
        return self._queue.qsize()

    async def _update_component_last_used_at_by_task(
        self, task_id: str, tenant_id: str, session: AsyncSession | None = None
    ) -> None:
        """Update the Component's last_used_at field when a task is executed."""
        from datetime import datetime

        from sqlalchemy import select, update

        from analysi.db.session import AsyncSessionLocal
        from analysi.models.component import Component
        from analysi.models.task import Task

        async def do_update(db_session: AsyncSession) -> None:
            # Update Component's last_used_at directly via task's component_id
            # First, get the component_id from the task
            task_subquery = select(Task.component_id).where(Task.id == task_id)

            # Update the Component using the component_id and tenant_id
            stmt = (
                update(Component)
                .where(Component.id.in_(task_subquery))
                .where(Component.tenant_id == tenant_id)
                .values(last_used_at=datetime.now(UTC))
            )
            await db_session.execute(stmt)

        if session:
            # Use the provided session
            await do_update(session)
        else:
            # Create a new session for the update
            async with AsyncSessionLocal() as update_session:
                await do_update(update_session)
                await update_session.commit()

    async def _worker(self) -> None:
        """Worker coroutine that processes tasks from the queue."""
        while True:
            try:
                # Get task from queue (this will wait if queue is empty)
                task_run = await asyncio.wait_for(self._queue.get(), timeout=1.0)

                # Execute the task and persist result to DB
                await self.execute_and_persist(task_run.id, task_run.tenant_id)

                # Mark task as done
                self._queue.task_done()

            except TimeoutError:
                # No tasks in queue, exit worker
                break
            except Exception as e:
                # Log error and continue
                logger.error("task_executor_worker_error", error=str(e))
                continue


class ExecutorConfigManager:
    """Manages executor configuration from environment variables."""

    @staticmethod
    def load_from_env() -> dict[str, Any]:
        """
        Load executor configuration from environment variables.

        Environment variables:
        - TASK_EXECUTOR_WORKERS: Number of concurrent async workers
        - TASK_EXECUTOR_TIMEOUT: Default timeout in seconds
        - ENABLED_EXECUTORS: Comma-separated list of enabled executor types

        Returns:
            Configuration dictionary
        """
        config = {
            "threads": int(os.getenv("TASK_EXECUTOR_WORKERS", "4")),
            "timeout": int(os.getenv("TASK_EXECUTOR_TIMEOUT", "300")),
            "enabled_executors": os.getenv("ENABLED_EXECUTORS", "default").split(","),
        }
        return config


class DurationCalculator:
    """Utility for calculating task execution durations."""

    @staticmethod
    def calculate(
        started_at: datetime | None, completed_at: datetime | None
    ) -> timedelta | None:
        """
        Calculate duration from start and end timestamps.

        Args:
            started_at: Task start timestamp
            completed_at: Task completion timestamp

        Returns:
            Duration as timedelta or None if invalid
        """
        if started_at is None or completed_at is None:
            return None

        if completed_at < started_at:
            return None

        return completed_at - started_at


class ExecutionContext:
    """Manages execution context for task runs."""

    @staticmethod
    def build_context(
        tenant_id: str,
        task_id: str | None,
        available_kus: list[str],
        workflow_run_id: str | None = None,
        workflow_node_instance_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Build execution context for a task run.

        Args:
            tenant_id: Tenant identifier
            task_id: Task identifier (None for ad-hoc)
            available_kus: List of available Knowledge Unit IDs
            workflow_run_id: Workflow run ID if task is part of workflow
            workflow_node_instance_id: Node instance ID if task is part of workflow

        Returns:
            Execution context dictionary
        """
        return {
            "tenant_id": tenant_id,
            "task_id": task_id,
            "workflow_run_id": workflow_run_id,
            "workflow_node_instance_id": workflow_node_instance_id,
            "knowledge_units": available_kus,
            "available_tools": [],  # Stub: will include MCP tools
            "llm_model": "gpt-4o-mini",
            "runtime_version": "cy-2.1",
        }
