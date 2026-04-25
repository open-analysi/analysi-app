---
name: test-writer-fixer
description: Write and fix fast, reliable tests for this Python/FastAPI/PostgreSQL project. Use when writing new unit/integration tests, fixing slow tests (>0.1s), or debugging flaky tests. Includes patterns from 83% test suite speedup (77s to 13s).
---

# Test Writer & Fixer Skill

Expert guidance for writing fast, reliable tests in this Python/FastAPI/PostgreSQL project.

## When to Use This Skill

- Writing new unit tests for integration actions
- Writing new integration tests for APIs
- Fixing slow tests (> 0.1s for unit tests)
- Debugging flaky or failing tests
- Reviewing test code for performance issues

## Core Principles

1. **Unit tests must be FAST** - Target < 0.1s per test
2. **Never use real delays** - Mock asyncio.sleep and retry decorators
3. **PostgreSQL only** - SQLite doesn't support our model features
4. **Specific exceptions** - Use httpx exception types, not generic Exception
5. **TDD workflow** - Write test, watch it fail, implement, watch it pass

## Progressive Workflow

### Level 1: Quick Test Write

**Use when**: Writing a straightforward test for a new feature.

**Steps**:
1. Identify test type (unit vs integration)
2. Copy pattern from `references/test-patterns-by-type.md`
3. Adapt fixtures and assertions
4. Run test: `pytest path/to/test.py -v`
5. Verify test is fast: `pytest path/to/test.py --durations=10`

**Example**:
```bash
# Write test for new action
pytest tests/unit/third_party_integrations/myservice/test_actions.py -v

# Check timing
pytest tests/unit/third_party_integrations/myservice/test_actions.py --durations=10
```

If any test takes > 0.1s, proceed to Level 2.

---

### Level 2: Fix Slow Test

**Use when**: Test takes > 0.1s (unit) or > 1s (integration).

**Decision Tree**:

```
Is test slow?
├─ Yes, takes 2-10 seconds
│  └─ Check: Does the code use @retry decorator?
│     ├─ Yes → Apply Pattern 1 (Tenacity Retry Mocking)
│     └─ No → Check: Does code have asyncio.sleep?
│        ├─ Yes → Apply Pattern 2 (Asyncio Sleep Mocking)
│        └─ No → Proceed to Level 3
├─ Yes, takes < 1 second but > 0.1s
│  └─ Check: Does test load files/manifests?
│     ├─ Yes → Apply Pattern 5 (Mock Framework Loading)
│     └─ No → Profile with --profile-svg
└─ No → Test is good!
```

**Quick Fixes**:

1. **Retry decorator delays** (2-10s per retry):
   ```python
   from tenacity import wait_fixed
   from module import decorated_function

   with patch.object(decorated_function.retry, "wait", wait_fixed(0)):
       await function()
   ```

2. **Polling delays** (sleep in loops):
   ```python
   with patch("asyncio.sleep", new_callable=AsyncMock):
       await polling_function()
   ```

3. **File I/O overhead** (0.5-1s):
   ```python
   with patch("module.RegistryService") as mock_registry:
       mock_registry.return_value.load.return_value = []
       await function()
   ```

See `references/test-speedup-patterns.md` for detailed examples.

---

### Level 3: Deep Test Debugging

**Use when**: Test is slow but cause is unclear.

**Steps**:

1. **Profile the test**:
   ```bash
   pytest tests/unit/path/test_file.py::test_name --profile-svg
   # Opens SVG flamegraph
   ```

2. **Check for anti-patterns**:
   - Review `references/unit-test-anti-patterns.md`
   - Run flakiness detector: `make detect-flakiness`

3. **Identify retry decorators**:
   ```bash
   # Find functions with @retry decorator
   grep -r "@retry" src/ | grep -v "test"
   ```

4. **Trace execution**:
   ```python
   import logging
   logging.basicConfig(level=logging.DEBUG)

   # Run test with debug output
   pytest tests/unit/path/test_file.py::test_name -vv -s
   ```

5. **Apply appropriate pattern** from references

---

### Level 4: Write Integration Test

**Use when**: Testing full API endpoints, database operations, or workflow execution.

**Decision Tree**:

```
What are you testing?
├─ API endpoints (CRUD only)
│  └─ Use standard client fixture (returns AsyncClient)
├─ Database operations
│  └─ Use integration_test_session fixture directly
└─ Workflow execution (end-to-end)
   └─ Use tuple client fixture (returns AsyncClient, AsyncSession)
```

**Checklist**:

- [ ] Mark with `@pytest.mark.integration`
- [ ] Use `integration_test_session` fixture
- [ ] Override `get_db` dependency for API tests
- [ ] Use unique IDs: `f"test-{uuid4().hex[:8]}"`
- [ ] Clean up dependency overrides
- [ ] If testing workflow execution: use tuple fixture `(client, session)`
- [ ] If testing workflow execution: commit before starting workflow
- [ ] If testing workflow execution: use manual execution pattern
- [ ] Use Valkey DB 100+ for queue tests (not 0-99)
- [ ] Test uses PostgreSQL (not SQLite)
- [ ] Timezone-aware timestamps

**Template (API endpoints)**:
```python
from collections.abc import AsyncGenerator
import pytest
from httpx import ASGITransport, AsyncClient
from uuid import uuid4

from analysi.db.session import get_db
from analysi.main import app


@pytest.mark.asyncio
@pytest.mark.integration
class TestMyAPI:
    """Test My API endpoints."""

    @pytest.fixture
    async def client(
        self, integration_test_session
    ) -> AsyncGenerator[AsyncClient, None]:
        """Create async HTTP client with test database."""
        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c

        app.dependency_overrides.clear()

    async def test_endpoint(self, client: AsyncClient):
        """Test endpoint."""
        tenant_id = f"tenant-{uuid4().hex[:8]}"

        response = await client.get(f"/v1/{tenant_id}/resources")

        assert response.status_code == 200
```

**Template (Workflow execution)**:
```python
@pytest.fixture
async def client(
    self, integration_test_session
) -> tuple[AsyncClient, AsyncSession]:
    """Create client AND return session for manual execution."""
    async def override_get_db():
        yield integration_test_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield (c, integration_test_session)  # Return tuple!

    app.dependency_overrides.clear()

async def test_workflow_execution(self, client):
    """Test workflow executes and produces results."""
    http_client, session = client  # Unpack tuple

    # 1. Create workflow via API
    workflow_id = await create_workflow(http_client)

    # 2. CRITICAL: Commit so background task can see data
    await session.commit()

    # 3. Start workflow
    response = await http_client.post(f"/.../workflows/{workflow_id}/run")
    workflow_run_id = response.json()["workflow_run_id"]

    # 4. Manual execution (avoids race conditions)
    from analysi.services.workflow_execution import WorkflowExecutor
    executor = WorkflowExecutor(session)
    await executor.monitor_execution(workflow_run_id)
    await session.commit()

    # 5. Verify results
    details = await http_client.get(f"/.../workflow-runs/{workflow_run_id}")
    assert details.json()["status"] == "completed"
```

See `references/integration-test-patterns.md` for detailed patterns and `references/test-patterns-by-type.md` for more examples.

---

## Common Tasks

### Task: Test New Integration Action

1. Copy pattern from `references/test-patterns-by-type.md` → "Testing Integration Actions"
2. Create fixtures for credentials and settings
3. Write success test first
4. Write error tests (timeout, connection error, auth error)
5. **Important**: Import decorated functions for retry mocking
6. Run: `pytest tests/unit/third_party_integrations/service/ --durations=10`
7. Verify all tests < 0.1s

### Task: Fix Test Taking 4+ Seconds

1. Identify if retry decorator is present:
   ```bash
   grep -A 5 "def.*_make_request" src/analysi/integrations/framework/integrations/service/actions.py
   ```

2. If `@retry` found:
   - Import the decorated function in test
   - Apply Pattern 1 from `references/test-speedup-patterns.md`

3. If `asyncio.sleep` found:
   - Apply Pattern 2 from `references/test-speedup-patterns.md`

4. Re-run with timing:
   ```bash
   pytest tests/unit/path/test.py::test_name --durations=1
   ```

### Task: Investigate Flaky Test

1. Check for hardcoded IDs:
   ```bash
   make detect-flakiness
   ```

2. Review anti-patterns:
   - See `references/unit-test-anti-patterns.md`
   - Check for shared tenant IDs
   - Check for generic Exception types

3. Add unique IDs:
   ```python
   from uuid import uuid4
   integration_id = f"test-int-{uuid4().hex[:8]}"
   ```

4. Run test 10 times to verify fix:
   ```bash
   pytest tests/path/test.py::test_name --count=10
   ```

---

## Reference Materials

### Quick Links

- **Speedup Patterns**: See `references/test-speedup-patterns.md`
  - 5 core patterns with examples
  - Quick reference table
  - Source code locations

- **Anti-Patterns**: See `references/unit-test-anti-patterns.md`
  - 10 common mistakes
  - Before-commit checklist
  - Code quality tools

- **Patterns by Type**: See `references/test-patterns-by-type.md`
  - Unit test templates
  - Integration test templates
  - Common fixtures

- **Integration Test Patterns**: See `references/integration-test-patterns.md`
  - Workflow execution testing (manual execution pattern)
  - Database operations with unique IDs
  - Valkey/Redis isolation (DB 100+)
  - API client fixtures
  - Common integration test mistakes

### Tools

```bash
# Find slow tests
pytest tests/unit/ --durations=20

# Detect flakiness
make detect-flakiness

# Test hygiene audit
make audit-test-hygiene

# CI quality check
make code-quality-ci

# Profile single test
pytest tests/unit/path/test.py::test_name --profile-svg
```

### Speed Targets

| Test Type | Target | Action if Slower |
|-----------|--------|------------------|
| Unit test | < 0.1s | Fix immediately |
| Integration test | < 2s | Investigate |
| Full unit suite | < 30s | Review slowest tests |

---

## Achievement Reference

This skill is based on real optimization work:

- **Original runtime**: 77 seconds
- **Final runtime**: 13 seconds
- **Improvement**: 83% faster (64 seconds saved)
- **Tests optimized**: 20 tests across 9 files
- **Individual speedups**: Up to 600x for slowest tests

See `FINAL_SPEEDUP_RESULTS.md` in project root for full details.

---

## Decision Tree Summary

```
Need to write/fix a test?
├─ Writing new test
│  ├─ Unit test? → Level 1 → Copy pattern from references
│  └─ Integration test? → Level 4 → Use integration template
├─ Test is slow
│  ├─ > 2s? → Level 2 → Apply retry/sleep mocking
│  ├─ > 0.1s? → Level 2 → Check file I/O
│  └─ Unclear? → Level 3 → Profile and debug
└─ Test is flaky
   └─ Level 3 → Check anti-patterns, run flakiness detector
```

---

## Next Steps After Using This Skill

1. **Run full suite timing**:
   ```bash
   pytest tests/unit/ --durations=0
   ```

2. **Check for regressions**:
   ```bash
   make code-quality-ci
   ```

3. **Update documentation** if you discovered new patterns

4. **Share findings** with team if you fixed complex issues
