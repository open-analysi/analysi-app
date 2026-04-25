"""
Integration test for LLM functions compilation.

Verifies that scripts using llm_run and other LLM functions compile successfully.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.mcp.context import set_tenant
from analysi.mcp.tools import cy_tools


@pytest.mark.asyncio
@pytest.mark.integration
async def test_llm_run_compiles(integration_test_session: AsyncSession):
    """
    Test that script using llm_run() compiles successfully.

    This reproduces the bug where llm_run was available at runtime but
    missing from compile-time tool registry.
    """
    script = """
# Simple LLM usage
prompt = "Analyze this alert: " + (input.alert_title ?? "unknown")
analysis = llm_run(prompt)
return {"analysis": analysis}
"""

    # Compile script
    # Set tenant context
    set_tenant("default")

    result = await cy_tools.compile_cy_script(script)

    print("\n=== LLM Run Compilation ===")
    print(f"Tools loaded: {result.get('tools_loaded', 0)}")
    print(f"Validation errors: {result.get('validation_errors')}")
    print(f"Plan: {'SUCCESS' if result['plan'] is not None else 'FAILED'}")

    # Should compile successfully
    assert result["plan"] is not None, (
        f"Script using llm_run should compile successfully. "
        f"Errors: {result.get('validation_errors')}"
    )

    assert len(result.get("validation_errors", [])) == 0, (
        f"Should have no validation errors. Got: {result.get('validation_errors')}"
    )

    print("\n✅ llm_run script compiled successfully")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_llm_run_with_optional_parameters(integration_test_session: AsyncSession):
    """Test that llm_run with optional parameters compiles."""
    script = """
# LLM with temperature parameter
analysis = llm_run(
    prompt="Analyze this",
    temperature=0.7,
    max_tokens=500
)
return {"analysis": analysis}
"""

    # Set tenant context
    set_tenant("default")

    result = await cy_tools.compile_cy_script(script)

    assert result["plan"] is not None
    assert len(result.get("validation_errors", [])) == 0

    print("\n✅ llm_run with optional parameters compiled successfully")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_llm_summarize_compiles(integration_test_session: AsyncSession):
    """Test that script using llm_summarize() compiles."""
    script = """
# Summarize alert details
alert_text = input.details ?? ""
summary = llm_summarize(alert_text, max_words=200)
return {"summary": summary}
"""

    # Set tenant context
    set_tenant("default")

    result = await cy_tools.compile_cy_script(script)

    assert result["plan"] is not None, (
        f"Script using llm_summarize should compile. "
        f"Errors: {result.get('validation_errors')}"
    )
    assert len(result.get("validation_errors", [])) == 0

    print("\n✅ llm_summarize script compiled successfully")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_llm_extract_compiles(integration_test_session: AsyncSession):
    """Test that script using llm_extract() compiles."""
    script = """
# Extract fields from text
alert_text = input.description ?? ""
extracted = llm_extract(alert_text, ["severity", "threat_type", "affected_systems"])
return {"extracted_data": extracted}
"""

    # Set tenant context
    set_tenant("default")

    result = await cy_tools.compile_cy_script(script)

    assert result["plan"] is not None, (
        f"Script using llm_extract should compile. "
        f"Errors: {result.get('validation_errors')}"
    )
    assert len(result.get("validation_errors", [])) == 0

    print("\n✅ llm_extract script compiled successfully")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_llm_evaluate_results_compiles(integration_test_session: AsyncSession):
    """Test that script using llm_evaluate_results() compiles."""
    script = """
# Evaluate analysis results
results = {"findings": ["suspicious IP", "malware detected"]}
evaluation = llm_evaluate_results(results, criteria="security threat level")
return {"evaluation": evaluation}
"""

    # Set tenant context
    set_tenant("default")

    result = await cy_tools.compile_cy_script(script)

    assert result["plan"] is not None, (
        f"Script using llm_evaluate_results should compile. "
        f"Errors: {result.get('validation_errors')}"
    )
    assert len(result.get("validation_errors", [])) == 0

    print("\n✅ llm_evaluate_results script compiled successfully")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_all_llm_functions_in_single_script(
    integration_test_session: AsyncSession,
):
    """Test script using all LLM functions together."""
    script = """
# Comprehensive LLM usage
alert_data = input.alert ?? {}

# Run analysis
analysis = llm_run("Analyze: " + (alert_data.title ?? "unknown"))

# Summarize
summary = llm_summarize(analysis, max_words=100)

# Extract structured data
extracted = llm_extract(analysis, ["severity", "recommendation"])

# Evaluate results
evaluation = llm_evaluate_results(extracted)

return {
    "analysis": analysis,
    "summary": summary,
    "extracted": extracted,
    "evaluation": evaluation
}
"""

    # Set tenant context
    set_tenant("default")

    result = await cy_tools.compile_cy_script(script)

    assert result["plan"] is not None, (
        f"Script using all LLM functions should compile. "
        f"Errors: {result.get('validation_errors')}"
    )
    assert len(result.get("validation_errors", [])) == 0

    print("\n✅ Script using all LLM functions compiled successfully")
