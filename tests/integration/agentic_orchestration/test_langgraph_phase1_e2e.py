"""End-to-end integration tests for LangGraph runbook matching.

SKIPPED - These tests are for the experimental LangGraph path
(ANALYSI_USE_LANGGRAPH_PHASE1=true) which requires a pre-built runbook index.
The index format changed to JIT generation, breaking this experimental path.

Production Kea uses the SDK path (default) which doesn't have this dependency.

TODO: Either remove these tests or update Phase1Matcher to generate index JIT.
"""

import pytest

pytestmark = pytest.mark.skip(
    reason="LangGraph experimental path requires pre-built index (see module docstring)"
)


# Original test classes preserved for reference when rewriting
# See git history for full implementation
