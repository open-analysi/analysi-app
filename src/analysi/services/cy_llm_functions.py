"""
Provider-agnostic Cy LLM functions that route through the Naxos integration framework.

All LLM calls go through IntegrationService.execute_action → framework actions
(anthropic_agent, openai, gemini). No LangChain dependency on the hot path.
"""

import json
import time
from typing import TYPE_CHECKING, Any
from uuid import UUID

from analysi.config.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    from analysi.schemas.task_execution import LLMUsage
    from analysi.services.feedback_relevance import FeedbackRelevanceService
    from analysi.services.integration_service import IntegrationService

logger = get_logger(__name__)


class CyLLMFunctions:
    """Native LLM functions for Cy scripts using Naxos integration framework."""

    def __init__(
        self,
        integration_service: "IntegrationService",
        execution_context: dict[str, Any],
    ):
        """
        Initialize Cy LLM functions with integration service.

        Args:
            integration_service: Service for executing integration actions
            execution_context: Current task/workflow execution context
        """
        self.integration_service = integration_service
        self.execution_context = execution_context
        # Extract session from context for reuse in credential operations
        self.session = execution_context.get("session")
        # Task directive used as system prompt for all LLM calls
        self.directive: str | None = execution_context.get("directive") or None
        # Accumulated LLM usage across all llm_run() calls in this task
        self._total_usage: LLMUsage | None = None
        # Analyst feedback entries for prompt augmentation
        self._feedback_entries: list[str] = execution_context.get(
            "feedback_entries", []
        )
        self._feedback_relevance_service: FeedbackRelevanceService | None = (
            execution_context.get("feedback_relevance_service")
        )
        # Cached primary AI integration info (resolved once, reused)
        self._primary_integration_id: str | None = None
        self._primary_integration_type: str | None = None
        self._primary_credential_id: UUID | None = None
        self._primary_resolved: bool = False

    async def _resolve_primary_ai_integration(
        self, tenant_id: str
    ) -> tuple[str, str, UUID | None]:
        """Find the primary AI integration and its credential for this tenant.

        Discovers all AI-archetype integrations, picks the one marked is_primary
        (or first available), and resolves the primary credential ID.

        Returns:
            Tuple of (integration_id, integration_type, credential_id).
        """
        if self._primary_resolved:
            return (
                self._primary_integration_id,  # type: ignore[return-value]
                self._primary_integration_type,  # type: ignore[return-value]
                self._primary_credential_id,
            )

        from analysi.integrations.framework.models import Archetype
        from analysi.integrations.framework.registry import get_registry

        ai_types = [m.id for m in get_registry().list_by_archetype(Archetype.AI)]

        integrations: list[Any] = []
        for ai_type in ai_types:
            integrations.extend(
                await self.integration_service.list_integrations(
                    tenant_id=tenant_id,
                    integration_type=ai_type,
                )
            )

        # Find primary integration
        primary = None
        for integration in integrations:
            settings = (
                integration.settings if hasattr(integration, "settings") else {}
            ) or {}
            if settings.get("is_primary", False):
                primary = integration
                break

        if not primary and integrations:
            primary = integrations[0]
            logger.warning(
                "no_primary_ai_integration_using_first",
                tenant_id=tenant_id,
                integration_id=getattr(primary, "integration_id", "unknown"),
            )

        if not primary:
            raise ValueError(
                f"No AI integrations configured for tenant {tenant_id}. "
                f"Please configure an AI integration ({', '.join(sorted(ai_types))}) "
                "via the integrations API."
            )

        self._primary_integration_id = primary.integration_id
        self._primary_integration_type = primary.integration_type

        # Resolve primary credential
        try:
            from analysi.repositories.credential_repository import (
                CredentialRepository,
            )

            if self.session:
                cred_repo = CredentialRepository(self.session)
                creds = await cred_repo.list_by_integration(
                    tenant_id, self._primary_integration_id
                )
                for ic in creds:
                    if ic.is_primary:
                        self._primary_credential_id = ic.credential_id
                        break
                if not self._primary_credential_id and creds:
                    self._primary_credential_id = creds[0].credential_id
        except Exception as e:
            logger.warning(
                "failed_to_resolve_primary_credential",
                error=str(e),
                integration_id=self._primary_integration_id,
            )

        self._primary_resolved = True
        logger.info(
            "resolved_primary_ai_integration",
            integration_id=self._primary_integration_id,
            integration_type=self._primary_integration_type,
        )

        return (
            self._primary_integration_id,
            self._primary_integration_type,
            self._primary_credential_id,
        )

    async def _resolve_integration(
        self, tenant_id: str, integration_id: str | None
    ) -> tuple[str, str, UUID | None]:
        """Resolve integration details for a specific or primary integration.

        Args:
            tenant_id: Tenant identifier
            integration_id: Explicit integration ID, or None for primary

        Returns:
            Tuple of (integration_id, integration_type, credential_id)
        """
        if not integration_id:
            return await self._resolve_primary_ai_integration(tenant_id)

        # Specific integration requested — look it up
        integration = await self.integration_service.get_integration(
            tenant_id, integration_id
        )
        if not integration:
            raise ValueError(
                f"Integration '{integration_id}' not found for tenant '{tenant_id}'"
            )

        resolved_type = integration.integration_type

        # Resolve credential for this integration
        credential_id = None
        try:
            from analysi.repositories.credential_repository import (
                CredentialRepository,
            )

            if self.session:
                cred_repo = CredentialRepository(self.session)
                creds = await cred_repo.list_by_integration(tenant_id, integration_id)
                for ic in creds:
                    if ic.is_primary:
                        credential_id = ic.credential_id
                        break
                if not credential_id and creds:
                    credential_id = creds[0].credential_id
        except Exception as e:
            logger.warning(
                "failed_to_resolve_credential",
                error=str(e),
                integration_id=integration_id,
            )

        return integration_id, resolved_type, credential_id

    async def llm_run(
        self,
        prompt: str,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        integration_id: str | None = None,
    ) -> str:
        """
        Run an LLM prompt using the Naxos integration framework.

        Routes through IntegrationService.execute_action → LlmRunAction for the
        configured AI provider (anthropic, openai, gemini).

        Args:
            prompt: The prompt to send to the LLM
            model: Optional model override (if supported by provider)
            temperature: Optional temperature override
            max_tokens: Optional max tokens override
            integration_id: Optional specific integration to use

        Returns:
            LLM response as string

        Raises:
            RuntimeError: If LLM execution fails
        """
        start_time = time.time()

        try:
            tenant_id = self.execution_context.get("tenant_id", "default")

            # Resolve which integration + credential to use
            resolved_id, resolved_type, credential_id = await self._resolve_integration(
                tenant_id, integration_id
            )

            # Augment prompt with relevant analyst feedback
            if self._feedback_entries:
                prompt = await self._augment_prompt_with_feedback(prompt)

            # Build params for framework action
            params: dict[str, Any] = {"prompt": prompt}
            if self.directive:
                params["context"] = self.directive
            if max_tokens is not None:
                params["override_max_tokens"] = max_tokens
            if temperature is not None:
                params["override_temperature"] = temperature

            # Execute via framework
            logger.info("executing_llm_prompt_length_chars", prompt_count=len(prompt))

            result = await self.integration_service.execute_action(
                tenant_id=tenant_id,
                integration_id=resolved_id,
                integration_type=resolved_type,
                action_id="llm_run",
                credential_id=credential_id,
                params=params,
                session=self.session,
            )

            # Extract response from framework result
            if isinstance(result, dict):
                if result.get("status") == "error":
                    raise RuntimeError(result.get("error", "LLM execution failed"))
                data = result.get("data", {})
                text = data.get("response", "") or str(data)
                input_tokens = data.get("input_tokens", 0)
                output_tokens = data.get("output_tokens", 0)
            else:
                text = str(result)
                input_tokens = 0
                output_tokens = 0

            logger.info("llm_response_received_length_chars", result_count=len(text))

            # Accumulate usage
            duration_ms = int((time.time() - start_time) * 1000)
            call_usage = self._accumulate_usage(input_tokens, output_tokens, model)

            # Fire-and-forget artifact capture
            await self._create_llm_artifact(
                function_name="llm_run",
                integration_id=resolved_id,
                prompt=prompt,
                completion=text,
                model=model,
                duration_ms=duration_ms,
                llm_usage=call_usage,
            )

            return text

        except RuntimeError:
            raise
        except Exception as e:
            logger.error("llm_execution_failed", error=str(e))
            raise RuntimeError(f"LLM execution failed: {e}")

    async def llm_evaluate_results(
        self,
        results: Any,
        criteria: str | None = None,
        integration_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Evaluate results using LLM.

        Args:
            results: Results to evaluate (will be JSON serialized)
            criteria: Optional evaluation criteria
            integration_id: Optional specific integration to use

        Returns:
            Evaluation results as dictionary
        """
        # Serialize results if needed
        if not isinstance(results, str):
            results_str = json.dumps(results, indent=2)
        else:
            results_str = results

        # Build evaluation prompt
        prompt = f"""Evaluate the following results:

Results:
{results_str}

"""
        if criteria:
            prompt += f"""Evaluation Criteria:
{criteria}

"""
        prompt += """Provide a structured evaluation with:
1. Summary of the results
2. Key findings
3. Any issues or concerns
4. Recommendations

Return the evaluation as a JSON object with keys: summary, findings, issues, recommendations"""

        # Run LLM
        response = await self.llm_run(
            prompt=prompt,
            integration_id=integration_id,
        )

        # Try to parse as JSON
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            # If not valid JSON, return as text
            return {
                "summary": response,
                "findings": [],
                "issues": [],
                "recommendations": [],
            }

    async def llm_summarize(
        self,
        text: str,
        context: str | None = None,
        directive: str | None = None,
        max_words: int = 20,
        integration_id: str | None = None,
    ) -> str:
        """
        Generate a concise summary of text with optional context.

        This function is used both as a native Cy function for tasks and
        by the post-task hooks for auto-generating ai_analysis_title.

        Args:
            text: Text to summarize
            context: Optional additional context to inform the summary
            directive: Optional system prompt to guide summarization style
            max_words: Maximum words in summary (default: 20)
            integration_id: Optional specific integration to use

        Returns:
            Summary as string
        """
        # Build user prompt
        user_prompt = f"Summarize the following in {max_words} words or less"
        if context:
            user_prompt += f".\n\nContext:\n{context}"
        user_prompt += f"\n\nText to summarize:\n{text}\n\nSummary:"

        # If a summarize-specific directive is provided, temporarily override
        # the context directive so llm_run uses it as the SystemMessage.
        if directive:
            original_directive = self.directive
            self.directive = directive
            try:
                return await self.llm_run(
                    prompt=user_prompt,
                    integration_id=integration_id,
                    max_tokens=100,  # Keep it short
                )
            finally:
                self.directive = original_directive
        else:
            return await self.llm_run(
                prompt=user_prompt,
                integration_id=integration_id,
                max_tokens=100,  # Keep it short
            )

    async def llm_extract(
        self,
        text: str,
        fields: list[str],
        integration_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Extract structured data from text.

        Args:
            text: Text to extract from
            fields: List of fields to extract
            integration_id: Optional specific integration to use

        Returns:
            Dictionary of extracted fields
        """
        fields_str = ", ".join(fields)
        prompt = f"""Extract the following fields from the text: {fields_str}

Text:
{text}

Return the results as a JSON object with the requested fields as keys."""

        response = await self.llm_run(
            prompt=prompt,
            integration_id=integration_id,
        )

        try:
            return json.loads(response)
        except json.JSONDecodeError:
            # Return empty dict if parsing fails
            logger.warning("Failed to parse LLM extraction response as JSON")
            return dict.fromkeys(fields)

    async def _augment_prompt_with_feedback(self, prompt: str) -> str:
        """Augment prompt with relevant analyst feedback.

        If a FeedbackRelevanceService is available, only relevant feedback
        is included. Otherwise all feedback entries are injected.
        Failures are swallowed — prompt is returned unmodified.

        Args:
            prompt: The original user/task prompt.

        Returns:
            Augmented prompt with feedback block prepended, or original prompt.
        """
        if not self._feedback_entries:
            return prompt

        try:
            if self._feedback_relevance_service:
                llm_callable = self._create_relevance_llm_callable()
                relevant = await self._feedback_relevance_service.get_relevant_feedback(
                    prompt, self._feedback_entries, llm_callable
                )
            else:
                # No relevance service — include all feedback as fallback
                relevant = list(self._feedback_entries)

            if not relevant:
                return prompt

            feedback_block = "\n".join(f"- {fb}" for fb in relevant)
            return (
                f"ANALYST FEEDBACK (takes precedence over default instructions):\n"
                f"{feedback_block}\n\n"
                f"TASK PROMPT:\n{prompt}"
            )
        except Exception as e:
            logger.warning("feedback_augmentation_failed", error=str(e))
            return prompt

    def _create_relevance_llm_callable(
        self,
    ) -> "Callable[[str], Coroutine[Any, Any, str]]":
        """Create a lightweight LLM callable for relevance checks.

        Returns a coroutine that invokes llm_run with no directive — bypassing
        artifact creation via a minimal prompt to keep overhead low.
        """

        async def _call(relevance_prompt: str) -> str:
            # Use llm_run directly — no directive, no feedback augmentation
            # Save and clear directive/feedback to avoid recursion
            saved_directive = self.directive
            saved_feedback = self._feedback_entries
            self.directive = None
            self._feedback_entries = []
            try:
                return await self.llm_run(relevance_prompt)
            finally:
                self.directive = saved_directive
                self._feedback_entries = saved_feedback

        return _call

    def get_total_usage(self) -> "LLMUsage | None":
        """Return accumulated token usage across all llm_run() calls.

        Returns:
            LLMUsage with aggregated totals, or None if no llm_run() calls were made.
        """
        return self._total_usage

    def _accumulate_usage(
        self,
        input_tokens: int,
        output_tokens: int,
        model: str | None,
    ) -> "LLMUsage | None":
        """Accumulate token usage from framework response into running total.

        Args:
            input_tokens: Prompt tokens from framework response.
            output_tokens: Completion tokens from framework response.
            model: Model name for cost lookup.

        Returns:
            LLMUsage for this single call, or None on failure.
        """
        from analysi.schemas.task_execution import LLMUsage
        from analysi.services.llm_pricing import pricing_registry

        try:
            if input_tokens == 0 and output_tokens == 0:
                return None

            total_tokens = input_tokens + output_tokens

            call_usage = pricing_registry.compute_usage(
                model, input_tokens, output_tokens
            )
            call_usage = LLMUsage(
                input_tokens=call_usage.input_tokens,
                output_tokens=call_usage.output_tokens,
                total_tokens=total_tokens,
                cost_usd=call_usage.cost_usd,
            )

            # Accumulate into running total
            if self._total_usage is None:
                self._total_usage = call_usage
            else:
                self._total_usage = self._total_usage.add(call_usage)

            return call_usage

        except Exception as e:
            logger.warning("failed_to_accumulate_llm_usage", error=str(e))
            return None

    async def _create_llm_artifact(
        self,
        function_name: str,
        integration_id: str,
        prompt: str,
        completion: str,
        model: str | None,
        duration_ms: int,
        llm_usage: "LLMUsage | None" = None,
    ) -> None:
        """
        Fire-and-forget helper to create LLM execution artifact.

        This captures the prompt/completion for audit and debugging purposes.
        Failures are logged but don't break the LLM execution flow.
        """
        try:
            from analysi.services.artifact_service import ArtifactService

            if not self.session:
                logger.debug("No session available for LLM artifact capture")
                return

            tenant_id = self.execution_context.get("tenant_id")
            if not tenant_id:
                logger.debug("No tenant_id in context for LLM artifact capture")
                return

            # Helper to safely convert string to UUID
            def safe_uuid(val: str | None) -> UUID | None:
                if not val:
                    return None
                try:
                    return UUID(val) if isinstance(val, str) else val
                except (ValueError, TypeError):
                    return None

            artifact_svc = ArtifactService(self.session)
            await artifact_svc.create_llm_execution_artifact(
                tenant_id=tenant_id,
                function_name=function_name,
                integration_id=integration_id,
                prompt=prompt,
                completion=completion,
                model=model,
                duration_ms=duration_ms,
                llm_usage=llm_usage,
                analysis_id=safe_uuid(self.execution_context.get("analysis_id")),
                task_run_id=safe_uuid(self.execution_context.get("task_run_id")),
                workflow_run_id=safe_uuid(
                    self.execution_context.get("workflow_run_id")
                ),
                workflow_node_instance_id=safe_uuid(
                    self.execution_context.get("workflow_node_instance_id")
                ),
            )
        except Exception as e:
            logger.warning("failed_to_create_llm_execution_artifact", error=str(e))


def create_cy_llm_functions(
    integration_service: "IntegrationService",
    execution_context: dict[str, Any],
) -> tuple[dict[str, Any], "CyLLMFunctions"]:
    """
    Create dictionary of native LLM functions to pass to Cy interpreter.

    Returns a tuple (functions_dict, instance) so callers can retrieve
    accumulated LLM usage via instance.get_total_usage() after execution.

    Args:
        integration_service: Service for executing integration actions
        execution_context: Current execution context

    Returns:
        Tuple of (functions dict for Cy interpreter, CyLLMFunctions instance)
    """
    cy_functions = CyLLMFunctions(integration_service, execution_context)

    functions = {
        "llm_run": cy_functions.llm_run,
        "llm_evaluate_results": cy_functions.llm_evaluate_results,
        "llm_summarize": cy_functions.llm_summarize,
        "llm_extract": cy_functions.llm_extract,
    }
    return functions, cy_functions
