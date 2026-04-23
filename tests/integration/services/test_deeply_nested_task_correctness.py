"""
Integration tests for deeply nested task execution correctness.

Validates session isolation and subroutine model contracts under deep nesting scenarios using
Cy scripts to drive nested task_run() calls. Covers:

- Multi-level data transformation correctness (3+ levels)
- Error propagation across nesting boundaries
- enrich_alert behaviour in nested tasks
- log() capture from every nesting level
- Context propagation (cy_name, task_call_depth)
- Mixed return types through nesting (dicts, lists, scalars)
- Fan-out: parent calling multiple children sequentially
- Child failure does not corrupt parent output
"""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.repositories.task import TaskRepository
from analysi.schemas.task_execution import TaskExecutionResult, TaskExecutionStatus
from analysi.services.task_execution import TaskExecutionService
from analysi.services.task_run import TaskRunService
from tests.utils.cy_output import parse_cy_output

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _register_task(
    session: AsyncSession,
    tenant_id: str,
    cy_name: str,
    script: str,
) -> None:
    """Create a Task record (no TaskRun)."""
    repo = TaskRepository(session)
    await repo.create(
        {
            "tenant_id": tenant_id,
            "name": f"Test — {cy_name}",
            "cy_name": cy_name,
            "script": script,
        }
    )
    await session.commit()


async def _execute_task(
    session: AsyncSession,
    tenant_id: str,
    cy_name: str,
    script: str,
    input_data: dict,
) -> TaskExecutionResult:
    """Create Task + TaskRun, execute via TaskExecutionService, return result."""
    repo = TaskRepository(session)
    task = await repo.create(
        {
            "tenant_id": tenant_id,
            "name": f"Test — {cy_name}",
            "cy_name": cy_name,
            "script": script,
        }
    )
    await session.commit()

    task_run_service = TaskRunService()
    task_run = await task_run_service.create_execution(
        session=session,
        tenant_id=tenant_id,
        task_id=task.component_id,
        cy_script=None,
        input_data=input_data,
        executor_config=None,
    )
    await session.commit()

    service = TaskExecutionService()
    return await service.execute_single_task(task_run.id, tenant_id)


# ===========================================================================
# Multi-level data transformation correctness
# ===========================================================================


@pytest.mark.asyncio
@pytest.mark.integration
class TestDeepDataTransformation:
    """Verify data flows correctly through 3-4 levels of nesting."""

    async def test_three_level_arithmetic_chain(
        self, integration_test_session: AsyncSession
    ):
        """
        A → B → C chain with arithmetic at each level.

        C: x * 3
        B: C(x) + 100
        A: B(x) + 1000

        Input x=7: C=21, B=121, A=1121
        """
        tid = f"deep-arith-{uuid4().hex[:8]}"

        await _register_task(
            integration_test_session,
            tid,
            cy_name="level_c_triple",
            script='return input["x"] * 3',
        )
        await _register_task(
            integration_test_session,
            tid,
            cy_name="level_b_add_hundred",
            script='v = task_run("level_c_triple", {"x": input["x"]})\nreturn v + 100',
        )
        result = await _execute_task(
            integration_test_session,
            tid,
            cy_name="level_a_root",
            script='v = task_run("level_b_add_hundred", {"x": input["x"]})\nreturn v + 1000',
            input_data={"x": 7},
        )

        assert result.status == TaskExecutionStatus.COMPLETED, result.error_message
        assert result.output_data == 1121  # 7*3=21, 21+100=121, 121+1000=1121

    async def test_four_level_dict_enrichment(
        self, integration_test_session: AsyncSession
    ):
        """
        4-level chain where each level adds a key to a dict.

        D: {"d": input["seed"]}
        C: merge D's result with {"c": "added_by_c"}
        B: merge C's result with {"b": "added_by_b"}
        A: merge B's result with {"a": "added_by_a"}

        Result should contain all 4 keys.
        """
        tid = f"deep-dict-{uuid4().hex[:8]}"

        await _register_task(
            integration_test_session,
            tid,
            cy_name="dict_d",
            script="""
result = {"d": input["seed"]}
return result
""",
        )
        await _register_task(
            integration_test_session,
            tid,
            cy_name="dict_c",
            script="""
child = task_run("dict_d", {"seed": input["seed"]})
child["c"] = "added_by_c"
return child
""",
        )
        await _register_task(
            integration_test_session,
            tid,
            cy_name="dict_b",
            script="""
child = task_run("dict_c", {"seed": input["seed"]})
child["b"] = "added_by_b"
return child
""",
        )
        result = await _execute_task(
            integration_test_session,
            tid,
            cy_name="dict_a",
            script="""
child = task_run("dict_b", {"seed": input["seed"]})
child["a"] = "added_by_a"
return child
""",
            input_data={"seed": 42},
        )

        assert result.status == TaskExecutionStatus.COMPLETED, result.error_message
        output = parse_cy_output(result.output_data)
        assert output["d"] == 42
        assert output["c"] == "added_by_c"
        assert output["b"] == "added_by_b"
        assert output["a"] == "added_by_a"

    async def test_three_level_list_aggregation(
        self, integration_test_session: AsyncSession
    ):
        """
        Each level appends to a list, verifying list data flows through nesting.

        C: returns [input["tag"]]
        B: gets C's list, appends own tag
        A: gets B's list, appends own tag

        Input: {"tag": "leaf"}
        Expected: ["leaf", "middle", "root"]
        """
        tid = f"deep-list-{uuid4().hex[:8]}"

        await _register_task(
            integration_test_session,
            tid,
            cy_name="list_leaf",
            script="""
items = [input["tag"]]
return items
""",
        )
        await _register_task(
            integration_test_session,
            tid,
            cy_name="list_middle",
            script="""
items = task_run("list_leaf", {"tag": input["tag"]})
items = items + ["middle"]
return items
""",
        )
        result = await _execute_task(
            integration_test_session,
            tid,
            cy_name="list_root",
            script="""
items = task_run("list_middle", {"tag": input["tag"]})
items = items + ["root"]
return items
""",
            input_data={"tag": "leaf"},
        )

        assert result.status == TaskExecutionStatus.COMPLETED, result.error_message
        assert parse_cy_output(result.output_data) == ["leaf", "middle", "root"]


# ===========================================================================
# Error propagation across nesting boundaries
# ===========================================================================


@pytest.mark.asyncio
@pytest.mark.integration
class TestNestedErrorPropagation:
    """Verify errors propagate correctly through nested task_run calls."""

    async def test_child_failure_propagates_to_parent(
        self, integration_test_session: AsyncSession
    ):
        """
        Child task fails; parent should still return a result
        (the error dict from the child).
        """
        tid = f"deep-err-{uuid4().hex[:8]}"

        await _register_task(
            integration_test_session,
            tid,
            cy_name="failing_child",
            script="""
x = 1 / 0
return x
""",
        )
        result = await _execute_task(
            integration_test_session,
            tid,
            cy_name="parent_calls_failing",
            script="""
child_result = task_run("failing_child", {})
return child_result
""",
            input_data={},
        )

        # Parent execution fails because child failed and error propagates
        # The result includes the error from the child
        if result.status == TaskExecutionStatus.COMPLETED:
            # If parent completed, the output should contain the child's error
            output = parse_cy_output(result.output_data)
            assert isinstance(output, dict)
            assert output.get("status") == "failed"
        else:
            # Parent might also fail — that's acceptable
            assert result.status == TaskExecutionStatus.FAILED

    async def test_grandchild_failure_propagates_two_levels(
        self, integration_test_session: AsyncSession
    ):
        """
        Grandchild fails (division by zero) → child returns error dict →
        parent returns error dict. Validates error doesn't get swallowed.
        """
        tid = f"deep-err2-{uuid4().hex[:8]}"

        await _register_task(
            integration_test_session,
            tid,
            cy_name="err_grandchild",
            script="""
x = 1 / 0
return x
""",
        )
        await _register_task(
            integration_test_session,
            tid,
            cy_name="err_child",
            script="""
result = task_run("err_grandchild", input)
return result
""",
        )
        result = await _execute_task(
            integration_test_session,
            tid,
            cy_name="err_parent",
            script="""
result = task_run("err_child", input)
return result
""",
            input_data={"some_data": 1},
        )

        # Error should propagate — result shouldn't be a clean success
        if result.status == TaskExecutionStatus.COMPLETED:
            output = parse_cy_output(result.output_data)
            # The error dict from the grandchild propagates through
            assert isinstance(output, dict), (
                f"Expected error dict, got {type(output)}: {output}"
            )
            assert output.get("status") == "failed", (
                f"Expected failed status, got: {output}"
            )
        else:
            assert result.status == TaskExecutionStatus.FAILED

    async def test_partial_success_one_child_fails_one_succeeds(
        self, integration_test_session: AsyncSession
    ):
        """
        Parent calls two children sequentially. First succeeds, second fails.
        Parent should still be able to return partial results.
        """
        tid = f"deep-partial-{uuid4().hex[:8]}"

        await _register_task(
            integration_test_session,
            tid,
            cy_name="good_child",
            script='return {"value": 42}',
        )
        await _register_task(
            integration_test_session,
            tid,
            cy_name="bad_child",
            script="""
x = 1 / 0
return x
""",
        )
        result = await _execute_task(
            integration_test_session,
            tid,
            cy_name="partial_parent",
            script="""
good = task_run("good_child", {})
bad = task_run("bad_child", {})
return {"good_result": good, "bad_result": bad}
""",
            input_data={},
        )

        # The parent completes (it doesn't raise on child failure by default —
        # task_run returns the error dict). The output should show both results.
        if result.status == TaskExecutionStatus.COMPLETED:
            output = parse_cy_output(result.output_data)
            good_result = parse_cy_output(output["good_result"])
            assert good_result["value"] == 42
            # bad_result should be a failure dict
            bad = parse_cy_output(output["bad_result"])
            assert isinstance(bad, dict)
            assert bad.get("status") == "failed"
        else:
            # If the parent itself failed, that's also acceptable
            assert result.status == TaskExecutionStatus.FAILED


# ===========================================================================
# enrich_alert in nested tasks
# ===========================================================================


@pytest.mark.asyncio
@pytest.mark.integration
class TestEnrichAlertInNestedTasks:
    """Verify enrich_alert works correctly when called from nested tasks."""

    async def test_nested_enrich_alert_uses_parent_cy_name(
        self, integration_test_session: AsyncSession
    ):
        """
        Child task calls enrich_alert. The enrichment key uses the
        parent's cy_name because nested calls are subroutines that
        inherit the parent's execution context (subroutine model design).
        """
        tid = f"deep-enrich-{uuid4().hex[:8]}"

        await _register_task(
            integration_test_session,
            tid,
            cy_name="enricher_child",
            script="""
alert = input
enrichment = {"threat_score": 85, "verdict": "suspicious"}
result = enrich_alert(alert, enrichment)
return result
""",
        )
        result = await _execute_task(
            integration_test_session,
            tid,
            cy_name="enricher_parent",
            script="""
enriched = task_run("enricher_child", input)
return enriched
""",
            input_data={"title": "Test Alert", "severity": "high"},
        )

        assert result.status == TaskExecutionStatus.COMPLETED, result.error_message
        output = parse_cy_output(result.output_data)
        assert "enrichments" in output
        # Subroutine model: child's enrich_alert uses the parent's cy_name
        # because child inherits the parent's execution context (cy_name is
        # NOT updated for nested calls — they're subroutines, not independent tasks)
        assert "enricher_parent" in output["enrichments"], (
            f"Expected 'enricher_parent' in enrichments (subroutine model), "
            f"got: {list(output['enrichments'].keys())}"
        )
        enrichment = output["enrichments"]["enricher_parent"]
        assert enrichment["threat_score"] == 85
        assert enrichment["verdict"] == "suspicious"

    async def test_two_level_enrich_with_explicit_keys(
        self, integration_test_session: AsyncSession
    ):
        """
        Both parent and child call enrich_alert with explicit key_name args
        to create distinct enrichment entries. This is the correct pattern
        when both levels need separate enrichment entries.
        """
        tid = f"deep-enrich2-{uuid4().hex[:8]}"

        await _register_task(
            integration_test_session,
            tid,
            cy_name="inner_enricher",
            script="""
alert = input
enrichment = {"source": "inner", "score": 10}
result = enrich_alert(alert, enrichment, "inner_analysis")
return result
""",
        )
        result = await _execute_task(
            integration_test_session,
            tid,
            cy_name="outer_enricher",
            script="""
alert = task_run("inner_enricher", input)
enrichment = {"source": "outer", "score": 20}
result = enrich_alert(alert, enrichment, "outer_analysis")
return result
""",
            input_data={"title": "Multi-Enrich Alert"},
        )

        assert result.status == TaskExecutionStatus.COMPLETED, result.error_message
        output = parse_cy_output(result.output_data)
        enrichments = output.get("enrichments", {})

        # Inner enrichment keyed by explicit key_name
        assert "inner_analysis" in enrichments, (
            f"Missing inner enrichment. Keys: {list(enrichments.keys())}"
        )
        assert enrichments["inner_analysis"]["source"] == "inner"

        # Outer enrichment keyed by explicit key_name
        assert "outer_analysis" in enrichments, (
            f"Missing outer enrichment. Keys: {list(enrichments.keys())}"
        )
        assert enrichments["outer_analysis"]["source"] == "outer"

        # Original alert fields preserved
        assert output.get("title") == "Multi-Enrich Alert"

    async def test_subroutine_enrich_overwrites_same_key(
        self, integration_test_session: AsyncSession
    ):
        """
        When both parent and child call enrich_alert without explicit keys,
        they both use the parent's cy_name (subroutine model). The child's
        enrichment is overwritten by the parent's — this documents the
        current behaviour as a known characteristic.
        """
        tid = f"deep-enrich3-{uuid4().hex[:8]}"

        await _register_task(
            integration_test_session,
            tid,
            cy_name="overwrite_child",
            script="""
alert = input
enrichment = {"from": "child", "score": 10}
result = enrich_alert(alert, enrichment)
return result
""",
        )
        result = await _execute_task(
            integration_test_session,
            tid,
            cy_name="overwrite_parent",
            script="""
alert = task_run("overwrite_child", input)
enrichment = {"from": "parent", "score": 20}
result = enrich_alert(alert, enrichment)
return result
""",
            input_data={"title": "Overwrite Test"},
        )

        assert result.status == TaskExecutionStatus.COMPLETED, result.error_message
        output = parse_cy_output(result.output_data)
        enrichments = output.get("enrichments", {})

        # Both use parent's cy_name → parent's enrichment overwrites child's
        assert "overwrite_parent" in enrichments
        assert enrichments["overwrite_parent"]["from"] == "parent"
        assert enrichments["overwrite_parent"]["score"] == 20


# ===========================================================================
# log() capture across nesting levels
# ===========================================================================


@pytest.mark.asyncio
@pytest.mark.integration
class TestLogCaptureInNestedTasks:
    """
    Verify that log() calls in the parent script are captured in the result.

    Note: log() calls in child tasks go to the child's captured_logs list.
    Only the parent's top-level log() calls appear in the TaskExecutionResult.log_entries.
    """

    async def test_parent_logs_captured_after_nested_calls(
        self, integration_test_session: AsyncSession
    ):
        """Parent calls log() before and after a nested task_run. Both captured."""
        tid = f"deep-log-{uuid4().hex[:8]}"

        await _register_task(
            integration_test_session,
            tid,
            cy_name="log_child",
            script='return {"computed": 99}',
        )
        result = await _execute_task(
            integration_test_session,
            tid,
            cy_name="log_parent",
            script="""
log("before child call")
child_result = task_run("log_child", {})
log("after child call")
return child_result
""",
            input_data={},
        )

        assert result.status == TaskExecutionStatus.COMPLETED, result.error_message
        assert parse_cy_output(result.output_data) == {"computed": 99}
        # Parent's log entries should be captured
        assert len(result.log_entries) >= 2
        # Log entries are dicts with {ts, message}
        messages = [
            e["message"] if isinstance(e, dict) else e for e in result.log_entries
        ]
        assert "before child call" in messages
        assert "after child call" in messages


# ===========================================================================
# Sequential fan-out: parent calls multiple children
# ===========================================================================


@pytest.mark.asyncio
@pytest.mark.integration
class TestSequentialFanOut:
    """Parent task calls multiple child tasks sequentially and aggregates."""

    async def test_parent_calls_three_children_and_aggregates(
        self, integration_test_session: AsyncSession
    ):
        """
        Parent calls A, B, C sequentially and merges their results into
        a single output dict.
        """
        tid = f"deep-fan-{uuid4().hex[:8]}"

        await _register_task(
            integration_test_session,
            tid,
            cy_name="fan_child_a",
            script='return {"from_a": input["x"] + 1}',
        )
        await _register_task(
            integration_test_session,
            tid,
            cy_name="fan_child_b",
            script='return {"from_b": input["x"] + 2}',
        )
        await _register_task(
            integration_test_session,
            tid,
            cy_name="fan_child_c",
            script='return {"from_c": input["x"] + 3}',
        )
        result = await _execute_task(
            integration_test_session,
            tid,
            cy_name="fan_parent",
            script="""
a = task_run("fan_child_a", {"x": input["x"]})
b = task_run("fan_child_b", {"x": input["x"]})
c = task_run("fan_child_c", {"x": input["x"]})
result = {"a": a, "b": b, "c": c}
return result
""",
            input_data={"x": 10},
        )

        assert result.status == TaskExecutionStatus.COMPLETED, result.error_message
        output = parse_cy_output(result.output_data)
        assert parse_cy_output(output["a"])["from_a"] == 11
        assert parse_cy_output(output["b"])["from_b"] == 12
        assert parse_cy_output(output["c"])["from_c"] == 13

    async def test_parent_chains_output_through_children(
        self, integration_test_session: AsyncSession
    ):
        """
        Parent calls children in sequence, piping each output to the next.

        A(5) → 10, B(10) → 30, C(30) → 31
        """
        tid = f"deep-chain-{uuid4().hex[:8]}"

        await _register_task(
            integration_test_session,
            tid,
            cy_name="chain_double",
            script='return input["v"] * 2',
        )
        await _register_task(
            integration_test_session,
            tid,
            cy_name="chain_triple",
            script='return input["v"] * 3',
        )
        await _register_task(
            integration_test_session,
            tid,
            cy_name="chain_increment",
            script='return input["v"] + 1',
        )
        result = await _execute_task(
            integration_test_session,
            tid,
            cy_name="chain_orchestrator",
            script="""
step1 = task_run("chain_double", {"v": input["v"]})
step2 = task_run("chain_triple", {"v": step1})
step3 = task_run("chain_increment", {"v": step2})
return step3
""",
            input_data={"v": 5},
        )

        assert result.status == TaskExecutionStatus.COMPLETED, result.error_message
        # 5*2=10, 10*3=30, 30+1=31
        assert result.output_data == 31


# ===========================================================================
# Mixed return types through nesting
# ===========================================================================


@pytest.mark.asyncio
@pytest.mark.integration
class TestMixedReturnTypes:
    """Children return various types; parent assembles them correctly."""

    async def test_children_return_scalar_list_dict(
        self, integration_test_session: AsyncSession
    ):
        """
        Three children return int, list, dict. Parent combines all three.
        """
        tid = f"deep-types-{uuid4().hex[:8]}"

        await _register_task(
            integration_test_session,
            tid,
            cy_name="returns_int",
            script="return 42",
        )
        await _register_task(
            integration_test_session,
            tid,
            cy_name="returns_list",
            script='return ["alpha", "beta"]',
        )
        await _register_task(
            integration_test_session,
            tid,
            cy_name="returns_dict",
            script='return {"key": "value"}',
        )
        result = await _execute_task(
            integration_test_session,
            tid,
            cy_name="type_aggregator",
            script="""
i = task_run("returns_int", {})
l = task_run("returns_list", {})
d = task_run("returns_dict", {})
return {"int_val": i, "list_val": l, "dict_val": d}
""",
            input_data={},
        )

        assert result.status == TaskExecutionStatus.COMPLETED, result.error_message
        output = parse_cy_output(result.output_data)
        assert output["int_val"] == 42
        assert parse_cy_output(output["list_val"]) == ["alpha", "beta"]
        assert parse_cy_output(output["dict_val"]) == {"key": "value"}

    async def test_string_return_through_nesting(
        self, integration_test_session: AsyncSession
    ):
        """
        Child returns a string; parent uses it in its own string.
        """
        tid = f"deep-str-{uuid4().hex[:8]}"

        await _register_task(
            integration_test_session,
            tid,
            cy_name="greet_child",
            script='return "world"',
        )
        result = await _execute_task(
            integration_test_session,
            tid,
            cy_name="greet_parent",
            script="""
who = task_run("greet_child", {})
return "hello " + who
""",
            input_data={},
        )

        assert result.status == TaskExecutionStatus.COMPLETED, result.error_message
        assert result.output_data == "hello world"


# ===========================================================================
# Deep nesting with conditional logic
# ===========================================================================


@pytest.mark.asyncio
@pytest.mark.integration
class TestDeepNestingWithConditionals:
    """Cy conditionals interact correctly with nested task_run calls."""

    async def test_conditional_task_dispatch(
        self, integration_test_session: AsyncSession
    ):
        """
        Parent dispatches to different children based on input.
        """
        tid = f"deep-cond-{uuid4().hex[:8]}"

        await _register_task(
            integration_test_session,
            tid,
            cy_name="handler_high",
            script='return {"priority": "high", "action": "escalate"}',
        )
        await _register_task(
            integration_test_session,
            tid,
            cy_name="handler_low",
            script='return {"priority": "low", "action": "monitor"}',
        )
        # Test high severity path
        result_high = await _execute_task(
            integration_test_session,
            tid,
            cy_name="cond_dispatcher_h",
            script="""
severity = input["severity"]
if (severity == "high") {
    result = task_run("handler_high", {})
} else {
    result = task_run("handler_low", {})
}
return result
""",
            input_data={"severity": "high"},
        )

        assert result_high.status == TaskExecutionStatus.COMPLETED, (
            result_high.error_message
        )
        assert parse_cy_output(result_high.output_data)["action"] == "escalate"

    async def test_conditional_task_dispatch_low_path(
        self, integration_test_session: AsyncSession
    ):
        """Same dispatcher but taking the low severity path."""
        tid = f"deep-cond-lo-{uuid4().hex[:8]}"

        await _register_task(
            integration_test_session,
            tid,
            cy_name="handler_high",
            script='return {"priority": "high", "action": "escalate"}',
        )
        await _register_task(
            integration_test_session,
            tid,
            cy_name="handler_low",
            script='return {"priority": "low", "action": "monitor"}',
        )
        result_low = await _execute_task(
            integration_test_session,
            tid,
            cy_name="cond_dispatcher_l",
            script="""
severity = input["severity"]
if (severity == "high") {
    result = task_run("handler_high", {})
} else {
    result = task_run("handler_low", {})
}
return result
""",
            input_data={"severity": "low"},
        )

        assert result_low.status == TaskExecutionStatus.COMPLETED, (
            result_low.error_message
        )
        assert parse_cy_output(result_low.output_data)["action"] == "monitor"


# ===========================================================================
# full_result=True in nested calls
# ===========================================================================


@pytest.mark.asyncio
@pytest.mark.integration
class TestFullResultFlag:
    """Validate task_run(... , True) returns full execution metadata."""

    async def test_full_result_includes_status_and_logs(
        self, integration_test_session: AsyncSession
    ):
        """
        Parent calls child with full_result=True and inspects the metadata.
        """
        tid = f"deep-full-{uuid4().hex[:8]}"

        await _register_task(
            integration_test_session,
            tid,
            cy_name="full_child",
            script="""
log("child log entry")
return {"answer": 42}
""",
        )
        result = await _execute_task(
            integration_test_session,
            tid,
            cy_name="full_parent",
            script="""
child = task_run("full_child", {}, True)
return {"child_status": child["status"], "child_output": child["output"]}
""",
            input_data={},
        )

        assert result.status == TaskExecutionStatus.COMPLETED, result.error_message
        output = parse_cy_output(result.output_data)
        assert output["child_status"] == "completed"
        child_output = parse_cy_output(output["child_output"])
        assert child_output["answer"] == 42
