# Integration Test Guidelines

## TaskRun Foreign Key Gotcha

**CRITICAL**: `TaskRun.task_id` references `task(component_id)`, NOT `task(id)`.

When creating a TaskRun in tests:
```python
# WRONG - will cause FK violation
task_run = TaskRun(task_id=task.id, ...)

# CORRECT - use the component_id
task_run = TaskRun(task_id=task.component_id, ...)
```

The FK constraint is defined as:
```sql
FOREIGN KEY (task_id) REFERENCES task(component_id)
```

## Session Management Pattern

For tests that execute tasks/workflows with background processing, follow the pattern from `DECISIONS.md` Decision 2:

```python
async def test_execution(self, session):
    # 1. Create test data
    task = await create_task(session)

    # 2. CRITICAL: Commit before execution
    await session.commit()

    # 3. Execute with same session (bypasses background task isolation)
    service = TaskExecutionService()
    await service.execute_single_task(task_run, session=session)

    # 4. Commit after execution
    await session.commit()

    # 5. Verify results
    ...
```

**Key insight**: `execute_single_task()` accepts an optional `session` parameter. When provided, it uses that session instead of creating its own. This enables integration tests to see data created during execution.

## Fixture Best Practices

When creating fixtures that provide task_id for TaskRun tests:
```python
@pytest.fixture
async def setup_task(session):
    component = Component(id=uuid4(), ...)
    session.add(component)

    task = Task(component_id=component.id, ...)
    session.add(task)

    await session.commit()  # Commit so FK validation succeeds

    return {
        # Return component.id for TaskRun.task_id, NOT task.id!
        "task_id": component.id,
    }
```
