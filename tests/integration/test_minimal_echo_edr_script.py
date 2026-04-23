"""
Test minimal echo_edr script compilation.

This test verifies that a minimal script using only the required 'ip' parameter compiles successfully.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.mcp.context import set_tenant
from analysi.mcp.tools import cy_tools


@pytest.mark.asyncio
@pytest.mark.integration
async def test_minimal_echo_edr_script_compiles(integration_test_session: AsyncSession):
    """
    Test that minimal echo_edr script with only required parameter compiles.

    This reproduces the exact script format that was failing.
    """
    script = """
# Minimal test: Echo EDR pull_browser_history with required parameter
result = app::echo_edr::pull_browser_history(ip="192.168.1.1")
return {"result": result}
"""

    # Compile script
    # Set tenant context
    set_tenant("default")

    result = await cy_tools.compile_cy_script(script)

    print("\n=== Minimal Echo EDR Script Compilation ===")
    print(f"Tools loaded: {result.get('tools_loaded', 0)}")
    print(f"Validation errors: {result.get('validation_errors')}")
    print(f"Plan: {'SUCCESS' if result['plan'] is not None else 'FAILED'}")

    # Should compile successfully
    assert result["plan"] is not None, (
        f"Minimal echo_edr script should compile successfully. "
        f"Errors: {result.get('validation_errors')}"
    )

    assert len(result.get("validation_errors", [])) == 0, (
        f"Should have no validation errors. Got: {result.get('validation_errors')}"
    )

    print("\n✅ Minimal echo_edr script compiled successfully")
