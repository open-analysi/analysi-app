"""
SDK Sanity Check - Fast verification of core SDK functionality.

This test runs FIRST in the eval suite (test_00_*) to catch SDK configuration
issues early before running expensive multi-stage workflow tests.

Verifies:
- claude-agent-sdk is properly installed and configured
- cwd parameter correctly sets working directory
- permission_mode allows file writes without prompts
- Basic file write operations work end-to-end

This test should complete in ~10 seconds and use minimal API credits.
If this fails, don't bother running the full eval suite.
"""

import tempfile
from pathlib import Path

import pytest

from analysi.agentic_orchestration.sdk_wrapper import AgentOrchestrationExecutor


@pytest.mark.eval
@pytest.mark.asyncio
async def test_sdk_writes_files(anthropic_api_key, isolated_claude_dir):
    """Sanity check: Verify SDK can write files with our configuration.

    This is a minimal smoke test that validates the SDK is working before
    running expensive multi-agent workflow tests.
    """
    # Create temp directory
    temp_dir = Path(tempfile.mkdtemp(prefix="sdk-test-"))

    print(f"\nTemp directory: {temp_dir}")

    # Create executor with isolated project dir to avoid loading project CLAUDE.md
    executor = AgentOrchestrationExecutor(
        api_key=anthropic_api_key,
        mcp_servers={},
        isolated_project_dir=isolated_claude_dir,
    )

    # Simple prompt asking to write a file
    from analysi.agentic_orchestration.observability import WorkflowGenerationStage

    prompt = f"""Write a file called 'test.txt' with the content 'Hello World' to the directory.

Working Directory: {temp_dir}
"""

    result, metrics = await executor.execute_stage(
        stage=WorkflowGenerationStage.RUNBOOK_GENERATION,
        system_prompt="You are a helpful assistant that follows instructions exactly.",
        user_prompt=prompt,
        cwd=str(temp_dir),
    )

    print(f"\nResult: {result}")
    print(f"Tool calls made: {len(metrics.tool_calls)}")

    # Check if file was created
    test_file = temp_dir / "test.txt"
    files_created = list(temp_dir.iterdir())

    print(f"Files in temp dir: {[f.name for f in files_created]}")

    assert test_file.exists(), f"File not created. Files in dir: {files_created}"

    content = test_file.read_text()
    print(f"File content: {content}")

    assert "Hello World" in content, f"Unexpected content: {content}"
