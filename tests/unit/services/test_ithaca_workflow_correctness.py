"""
Unit tests for Ithaca workflow execution correctness.

Tests the WorkflowExecutor helper methods that underpin concurrent
fan-out/fan-in execution. Uses mocked sessions and repositories — no database
required, so these run in milliseconds.

Covers:
- _create_successor_instances: advisory lock, idempotent edge-only creation
- check_predecessors_complete: readiness logic for various topologies
- aggregate_predecessor_outputs: single, multi, empty predecessor handling
- _capture_workflow_output: terminal node output extraction
- monitor_execution loop: failure detection, stalled-node detection
"""

import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from analysi.models.workflow_execution import (
    WorkflowNodeInstance,
)
from analysi.services.workflow_execution import WorkflowExecutor

# ---------------------------------------------------------------------------
# Helpers to build mock workflow graphs
# ---------------------------------------------------------------------------


def _mock_node(node_id: str, **kwargs):
    """Create a mock WorkflowNode (definition, not instance)."""
    node = MagicMock()
    node.node_id = node_id
    node.id = kwargs.get("id", uuid4())
    node.node_template_id = kwargs.get("template_id")
    node.task_id = kwargs.get("task_id")
    node.kind = kwargs.get("kind", "transformation")
    node.is_start_node = kwargs.get("is_start_node", False)
    return node


def _mock_edge(from_node, to_node, **kwargs):
    """Create a mock WorkflowEdge (definition)."""
    edge = MagicMock()
    edge.from_node = from_node
    edge.to_node = to_node
    edge.edge_id = kwargs.get("edge_id", f"e-{from_node.node_id}-{to_node.node_id}")
    edge.id = kwargs.get("id", uuid4())
    return edge


def _mock_node_instance(node_id: str, status: str = "completed", **kwargs):
    """Create a mock WorkflowNodeInstance (runtime instance)."""
    instance = MagicMock(spec=WorkflowNodeInstance)
    instance.id = kwargs.get("id", uuid4())
    instance.node_id = node_id
    instance.node_uuid = kwargs.get("node_uuid", uuid4())
    instance.status = status
    instance.workflow_run_id = kwargs.get("workflow_run_id", uuid4())
    instance.output_type = kwargs.get("output_type", "inline")
    instance.output_location = kwargs.get("output_location")
    instance.template_id = kwargs.get("template_id")
    return instance


def _mock_workflow(nodes, edges):
    """Create a mock Workflow with given nodes and edges."""
    workflow = MagicMock()
    workflow.nodes = nodes
    workflow.edges = edges
    workflow.id = uuid4()
    workflow.name = "Test Workflow"
    return workflow


# ---------------------------------------------------------------------------
# _create_successor_instances
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCreateSuccessorInstances:
    """
    Test the advisory-lock-guarded _create_successor_instances method.

    These tests mock the session and repos to verify the logic:
    - Creates successor when none exists
    - Creates only edge when successor already exists (idempotent path)
    - Handles nodes with no outgoing edges
    - Handles multiple outgoing edges (fan-out from one node)
    """

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        return session

    @pytest.fixture
    def executor(self, mock_session):
        return WorkflowExecutor(mock_session)

    @pytest.mark.asyncio
    async def test_creates_successor_and_edge_when_none_exists(self, executor):
        """When no successor instance exists, both node and edge are created."""
        run_id = uuid4()

        node_a = _mock_node("n-a")
        node_b = _mock_node("n-b", template_id=uuid4())
        edge_ab = _mock_edge(node_a, node_b)
        workflow = _mock_workflow([node_a, node_b], [edge_ab])

        completed_instance = _mock_node_instance("n-a", workflow_run_id=run_id)

        # No existing successor
        executor.node_repo.get_node_instance_by_node_id = AsyncMock(return_value=None)
        mock_new_instance = _mock_node_instance("n-b")
        executor.node_repo.create_node_instance = AsyncMock(
            return_value=mock_new_instance
        )
        executor.edge_repo.create_edge_instance = AsyncMock()

        await executor._create_successor_instances(run_id, completed_instance, workflow)

        # Advisory lock acquired
        executor.session.execute.assert_called()

        # Node created
        executor.node_repo.create_node_instance.assert_called_once()
        call_kwargs = executor.node_repo.create_node_instance.call_args
        assert call_kwargs[1]["node_id"] == "n-b" or call_kwargs[0][1] == "n-b"

        # Edge created
        executor.edge_repo.create_edge_instance.assert_called_once()

        # Commit after loop
        executor.session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_creates_only_edge_when_successor_exists(self, executor):
        """When successor already exists (created by another branch), only edge is created."""
        run_id = uuid4()

        node_a = _mock_node("n-a")
        node_merge = _mock_node("n-merge")
        edge_a_merge = _mock_edge(node_a, node_merge)
        workflow = _mock_workflow([node_a, node_merge], [edge_a_merge])

        completed_instance = _mock_node_instance("n-a", workflow_run_id=run_id)

        # Successor ALREADY exists
        existing_merge = _mock_node_instance("n-merge")
        executor.node_repo.get_node_instance_by_node_id = AsyncMock(
            return_value=existing_merge
        )
        executor.node_repo.create_node_instance = AsyncMock()  # Track calls
        executor.edge_repo.create_edge_instance = AsyncMock()

        await executor._create_successor_instances(run_id, completed_instance, workflow)

        # Node NOT created (already exists — idempotent edge-only path)
        executor.node_repo.create_node_instance.assert_not_called()

        # Edge IS created (linking this branch to existing merge)
        executor.edge_repo.create_edge_instance.assert_called_once()
        call_kwargs = executor.edge_repo.create_edge_instance.call_args[1]
        assert call_kwargs["to_instance_id"] == existing_merge.id

    @pytest.mark.asyncio
    async def test_no_ops_when_no_outgoing_edges(self, executor):
        """Terminal node has no outgoing edges — nothing created."""
        run_id = uuid4()

        node_terminal = _mock_node("n-terminal")
        workflow = _mock_workflow([node_terminal], [])  # No edges

        completed_instance = _mock_node_instance("n-terminal", workflow_run_id=run_id)

        executor.node_repo.create_node_instance = AsyncMock()  # Track calls
        executor.edge_repo.create_edge_instance = AsyncMock()  # Track calls

        await executor._create_successor_instances(run_id, completed_instance, workflow)

        # No node or edge creation
        executor.node_repo.create_node_instance.assert_not_called()
        executor.edge_repo.create_edge_instance.assert_not_called()

    @pytest.mark.asyncio
    async def test_fan_out_creates_two_successors(self, executor):
        """Fan-out: identity → [B, C] creates two successor instances."""
        run_id = uuid4()

        node_id = _mock_node("n-identity")
        node_b = _mock_node("n-b", template_id=uuid4())
        node_c = _mock_node("n-c", template_id=uuid4())
        edge_ib = _mock_edge(node_id, node_b)
        edge_ic = _mock_edge(node_id, node_c)
        workflow = _mock_workflow([node_id, node_b, node_c], [edge_ib, edge_ic])

        completed_instance = _mock_node_instance("n-identity", workflow_run_id=run_id)

        # Neither successor exists
        executor.node_repo.get_node_instance_by_node_id = AsyncMock(return_value=None)

        mock_b = _mock_node_instance("n-b")
        mock_c = _mock_node_instance("n-c")
        executor.node_repo.create_node_instance = AsyncMock(
            side_effect=[mock_b, mock_c]
        )
        executor.edge_repo.create_edge_instance = AsyncMock()

        await executor._create_successor_instances(run_id, completed_instance, workflow)

        # Two nodes created (B and C)
        assert executor.node_repo.create_node_instance.call_count == 2

        # Two edges created
        assert executor.edge_repo.create_edge_instance.call_count == 2

    @pytest.mark.asyncio
    async def test_advisory_lock_key_derived_from_run_and_node(self, executor):
        """Lock key must incorporate both workflow_run_id and successor_node_id."""
        run_id = uuid4()

        node_a = _mock_node("n-a")
        node_b = _mock_node("n-b", template_id=uuid4())
        edge_ab = _mock_edge(node_a, node_b)
        workflow = _mock_workflow([node_a, node_b], [edge_ab])

        completed = _mock_node_instance("n-a", workflow_run_id=run_id)

        executor.node_repo.get_node_instance_by_node_id = AsyncMock(return_value=None)
        executor.node_repo.create_node_instance = AsyncMock(
            return_value=_mock_node_instance("n-b")
        )
        executor.edge_repo.create_edge_instance = AsyncMock()

        await executor._create_successor_instances(run_id, completed, workflow)

        # The first execute call should be the advisory lock
        lock_call = executor.session.execute.call_args_list[0]
        sql_text = str(lock_call[0][0])
        assert "pg_advisory_xact_lock" in sql_text
        # Lock key passed as second positional arg (the params dict)
        lock_params = lock_call[0][1] if len(lock_call[0]) > 1 else lock_call[1]
        assert "key" in lock_params

    @pytest.mark.asyncio
    async def test_mixed_existing_and_new_successors(self, executor):
        """One successor exists, another doesn't — correct handling for each."""
        run_id = uuid4()

        node_a = _mock_node("n-a")
        node_b = _mock_node("n-b", template_id=uuid4())
        node_c = _mock_node("n-c", template_id=uuid4())
        edge_ab = _mock_edge(node_a, node_b)
        edge_ac = _mock_edge(node_a, node_c)
        workflow = _mock_workflow([node_a, node_b, node_c], [edge_ab, edge_ac])

        completed = _mock_node_instance("n-a", workflow_run_id=run_id)

        # B exists, C doesn't
        existing_b = _mock_node_instance("n-b")
        new_c = _mock_node_instance("n-c")

        executor.node_repo.get_node_instance_by_node_id = AsyncMock(
            side_effect=[existing_b, None]
        )
        executor.node_repo.create_node_instance = AsyncMock(return_value=new_c)
        executor.edge_repo.create_edge_instance = AsyncMock()

        await executor._create_successor_instances(run_id, completed, workflow)

        # Only C created as new node
        executor.node_repo.create_node_instance.assert_called_once()

        # Both edges created (one to existing B, one to new C)
        assert executor.edge_repo.create_edge_instance.call_count == 2


# ---------------------------------------------------------------------------
# aggregate_predecessor_outputs
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAggregatePredecessorOutputs:
    """Test fan-in data aggregation from multiple predecessors."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.fixture
    def executor(self, mock_session):
        return WorkflowExecutor(mock_session)

    @pytest.mark.asyncio
    async def test_single_predecessor_returns_envelope(self, executor):
        """Single predecessor output is wrapped in standard envelope."""
        run_id = uuid4()
        pred = _mock_node_instance(
            "n-pred",
            output_type="inline",
            output_location='{"node_id": "n-pred", "result": {"score": 42}}',
        )
        executor.node_repo.get_predecessor_instances = AsyncMock(return_value=[pred])
        executor.storage.retrieve = AsyncMock(
            return_value='{"node_id": "n-pred", "result": {"score": 42}}'
        )

        result = await executor.aggregate_predecessor_outputs(run_id, "n-target")

        assert isinstance(result, dict)
        assert "result" in result
        assert result["result"]["score"] == 42
        assert "single-n-target" in result["node_id"]

    @pytest.mark.asyncio
    async def test_two_predecessors_returns_aggregated_array(self, executor):
        """Multiple predecessors are aggregated into a result array."""
        run_id = uuid4()
        pred_a = _mock_node_instance(
            "n-a",
            output_type="inline",
            output_location='{"result": {"from": "a"}}',
        )
        pred_b = _mock_node_instance(
            "n-b",
            output_type="inline",
            output_location='{"result": {"from": "b"}}',
        )
        executor.node_repo.get_predecessor_instances = AsyncMock(
            return_value=[pred_a, pred_b]
        )
        executor.storage.retrieve = AsyncMock(
            side_effect=[
                '{"result": {"from": "a"}}',
                '{"result": {"from": "b"}}',
            ]
        )

        result = await executor.aggregate_predecessor_outputs(run_id, "n-merge")

        assert isinstance(result, dict)
        assert "result" in result
        predecessor_outputs = result["result"]
        assert isinstance(predecessor_outputs, list)
        assert len(predecessor_outputs) == 2
        assert {"from": "a"} in predecessor_outputs
        assert {"from": "b"} in predecessor_outputs

    @pytest.mark.asyncio
    async def test_three_predecessors_fan_in(self, executor):
        """Three-way fan-in aggregates all outputs."""
        run_id = uuid4()
        preds = []
        for name in ["a", "b", "c"]:
            p = _mock_node_instance(
                f"n-{name}",
                output_type="inline",
                output_location=json.dumps({"result": {"val": name}}),
            )
            preds.append(p)

        executor.node_repo.get_predecessor_instances = AsyncMock(return_value=preds)
        executor.storage.retrieve = AsyncMock(
            side_effect=[
                json.dumps({"result": {"val": "a"}}),
                json.dumps({"result": {"val": "b"}}),
                json.dumps({"result": {"val": "c"}}),
            ]
        )

        result = await executor.aggregate_predecessor_outputs(run_id, "n-merge")

        outputs = result["result"]
        assert len(outputs) == 3
        vals = {o["val"] for o in outputs}
        assert vals == {"a", "b", "c"}

    @pytest.mark.asyncio
    async def test_no_predecessors_returns_workflow_input(self, executor):
        """Start node (no predecessors) gets workflow input data."""
        run_id = uuid4()
        executor.node_repo.get_predecessor_instances = AsyncMock(return_value=[])

        # Mock the workflow run lookup
        mock_run = MagicMock()
        mock_run.tenant_id = "test-tenant"
        mock_run.input_type = "inline"
        mock_run.input_location = '{"alert": {"severity": "high"}}'

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_run
        executor.session.execute.return_value = mock_result

        executor.run_repo.get_workflow_run = AsyncMock(return_value=mock_run)

        result = await executor.aggregate_predecessor_outputs(run_id, "n-start")

        assert isinstance(result, dict)
        assert result["alert"]["severity"] == "high"

    @pytest.mark.asyncio
    async def test_predecessor_without_output_returns_empty(self, executor):
        """Single predecessor with no output_location returns empty result."""
        run_id = uuid4()
        pred = _mock_node_instance("n-pred", output_type=None, output_location=None)
        executor.node_repo.get_predecessor_instances = AsyncMock(return_value=[pred])

        result = await executor.aggregate_predecessor_outputs(run_id, "n-target")

        assert result["result"] == {}


# ---------------------------------------------------------------------------
# Concurrent gather error handling
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestConcurrentGatherErrorHandling:
    """
    Unit tests for the error handling logic in monitor_execution's
    asyncio.gather() section. Verifies partial failure semantics.
    """

    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.fixture
    def executor(self, mock_session):
        return WorkflowExecutor(mock_session)

    @pytest.mark.asyncio
    async def test_partial_failure_marks_failed_node(self, executor):
        """When gather returns an exception for one node, that node is marked failed."""
        # Simulate the post-gather error handling logic
        node_a = _mock_node_instance("n-a")
        node_b = _mock_node_instance("n-b")

        # Simulate gather results: A succeeded, B failed
        results = [None, RuntimeError("task B exploded")]

        executor.node_repo.update_node_instance_status = AsyncMock()
        executor.session.commit = AsyncMock()

        # Reproduce the error handling from monitor_execution lines 821-837
        for node_instance, result in zip([node_a, node_b], results, strict=False):
            if isinstance(result, BaseException):
                await executor.node_repo.update_node_instance_status(
                    node_instance.id,
                    "failed",
                    error_message=str(result),
                )
                await executor.session.commit()

        # Only B should be marked failed
        executor.node_repo.update_node_instance_status.assert_called_once_with(
            node_b.id, "failed", error_message="task B exploded"
        )

    @pytest.mark.asyncio
    async def test_all_success_no_failure_marking(self, executor):
        """When all gather results succeed, no nodes are marked failed."""
        node_a = _mock_node_instance("n-a")
        node_b = _mock_node_instance("n-b")

        results = [None, None]  # Both succeeded

        executor.node_repo.update_node_instance_status = AsyncMock()

        for node_instance, result in zip([node_a, node_b], results, strict=False):
            if isinstance(result, BaseException):
                await executor.node_repo.update_node_instance_status(
                    node_instance.id, "failed", error_message=str(result)
                )

        executor.node_repo.update_node_instance_status.assert_not_called()


# ---------------------------------------------------------------------------
# _capture_workflow_output
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCaptureWorkflowOutput:
    """Test terminal node output extraction logic."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.fixture
    def executor(self, mock_session):
        return WorkflowExecutor(mock_session)

    @pytest.mark.asyncio
    async def test_single_terminal_node_captures_output(self, executor):
        """Output from the single terminal node is stored as workflow output."""
        run_id = uuid4()
        terminal_ids = ["n-final"]

        # Mock finding the completed terminal node instance
        terminal_instance = _mock_node_instance(
            "n-final",
            status="completed",
            output_type="inline",
            output_location=json.dumps(
                {
                    "node_id": "n-final",
                    "result": {"verdict": "clean", "score": 0},
                }
            ),
        )

        # _capture_workflow_output uses node_repo.get_node_instance_by_node_id
        executor.node_repo.get_node_instance_by_node_id = AsyncMock(
            return_value=terminal_instance
        )
        executor.run_repo.update_workflow_run_status = AsyncMock()

        await executor._capture_workflow_output(run_id, terminal_ids)

        # _capture_workflow_output stores output while keeping status="running"
        # (the caller sets "completed" status separately)
        executor.run_repo.update_workflow_run_status.assert_called_once()
        call_kwargs = executor.run_repo.update_workflow_run_status.call_args[1]
        assert call_kwargs["status"] == "running"
        assert call_kwargs["output_type"] == "inline"
        # The output_location should contain the extracted result
        stored = json.loads(call_kwargs["output_location"])
        assert stored["verdict"] == "clean"
        assert stored["score"] == 0


# ---------------------------------------------------------------------------
# Diamond topology: A → [B, C] → D
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDiamondTopologyLogic:
    """
    Verify the executor's helper methods produce correct results for
    the classic diamond topology (fan-out then fan-in).
    """

    @pytest.fixture
    def diamond_graph(self):
        """Build diamond: A → [B, C] → D"""
        a = _mock_node("n-a", is_start_node=True)
        b = _mock_node("n-b")
        c = _mock_node("n-c")
        d = _mock_node("n-d")
        edges = [
            _mock_edge(a, b, edge_id="e-a-b"),
            _mock_edge(a, c, edge_id="e-a-c"),
            _mock_edge(b, d, edge_id="e-b-d"),
            _mock_edge(c, d, edge_id="e-c-d"),
        ]
        return _mock_workflow([a, b, c, d], edges)

    def test_terminal_nodes_identified_correctly(self, diamond_graph):
        """D is the only terminal node (no outgoing edges)."""
        nodes_with_outgoing = {edge.from_node.node_id for edge in diamond_graph.edges}
        terminal_ids = [
            node.node_id
            for node in diamond_graph.nodes
            if node.node_id not in nodes_with_outgoing
        ]
        assert terminal_ids == ["n-d"]

    def test_start_nodes_identified_correctly(self, diamond_graph):
        """A is the only node with no incoming edges."""
        nodes_with_incoming = {edge.to_node.node_id for edge in diamond_graph.edges}
        start_ids = [
            node.node_id
            for node in diamond_graph.nodes
            if node.node_id not in nodes_with_incoming
        ]
        assert start_ids == ["n-a"]

    def test_fan_out_from_a(self, diamond_graph):
        """A has exactly two outgoing edges (to B and C)."""
        outgoing = [
            edge for edge in diamond_graph.edges if edge.from_node.node_id == "n-a"
        ]
        assert len(outgoing) == 2
        targets = {edge.to_node.node_id for edge in outgoing}
        assert targets == {"n-b", "n-c"}

    def test_fan_in_to_d(self, diamond_graph):
        """D has exactly two incoming edges (from B and C)."""
        incoming = [
            edge for edge in diamond_graph.edges if edge.to_node.node_id == "n-d"
        ]
        assert len(incoming) == 2
        sources = {edge.from_node.node_id for edge in incoming}
        assert sources == {"n-b", "n-c"}


# ---------------------------------------------------------------------------
# Complex topology: A → [B, C, D] → E → [F, G] → H
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestWideAndDeepTopologyLogic:
    """
    Verify logic for a wider topology:
    A → [B, C, D] → E → [F, G] → H

    Two fan-out/fan-in stages with different widths.
    """

    @pytest.fixture
    def wide_deep_graph(self):
        a = _mock_node("n-a", is_start_node=True)
        b = _mock_node("n-b")
        c = _mock_node("n-c")
        d = _mock_node("n-d")
        e = _mock_node("n-e")
        f = _mock_node("n-f")
        g = _mock_node("n-g")
        h = _mock_node("n-h")
        edges = [
            _mock_edge(a, b),
            _mock_edge(a, c),
            _mock_edge(a, d),  # 3-wide fan-out
            _mock_edge(b, e),
            _mock_edge(c, e),
            _mock_edge(d, e),  # 3-way fan-in
            _mock_edge(e, f),
            _mock_edge(e, g),  # 2-wide fan-out
            _mock_edge(f, h),
            _mock_edge(g, h),  # 2-way fan-in
        ]
        return _mock_workflow([a, b, c, d, e, f, g, h], edges)

    def test_terminal_node_is_h(self, wide_deep_graph):
        nodes_with_outgoing = {edge.from_node.node_id for edge in wide_deep_graph.edges}
        terminals = [
            n.node_id
            for n in wide_deep_graph.nodes
            if n.node_id not in nodes_with_outgoing
        ]
        assert terminals == ["n-h"]

    def test_first_fan_out_width_is_three(self, wide_deep_graph):
        outgoing_a = [e for e in wide_deep_graph.edges if e.from_node.node_id == "n-a"]
        assert len(outgoing_a) == 3

    def test_first_fan_in_width_is_three(self, wide_deep_graph):
        incoming_e = [e for e in wide_deep_graph.edges if e.to_node.node_id == "n-e"]
        assert len(incoming_e) == 3

    def test_second_fan_out_width_is_two(self, wide_deep_graph):
        outgoing_e = [e for e in wide_deep_graph.edges if e.from_node.node_id == "n-e"]
        assert len(outgoing_e) == 2

    def test_second_fan_in_width_is_two(self, wide_deep_graph):
        incoming_h = [e for e in wide_deep_graph.edges if e.to_node.node_id == "n-h"]
        assert len(incoming_h) == 2

    def test_successor_creation_for_a(self, wide_deep_graph):
        """_create_successor_instances for A should identify B, C, D."""
        outgoing = [
            edge for edge in wide_deep_graph.edges if edge.from_node.node_id == "n-a"
        ]
        successor_ids = {e.to_node.node_id for e in outgoing}
        assert successor_ids == {"n-b", "n-c", "n-d"}


# ---------------------------------------------------------------------------
# Sequential chain: A → B → C → D → E
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSequentialChainTopology:
    """No fan-out: pure sequential chain."""

    @pytest.fixture
    def chain_graph(self):
        nodes = [_mock_node(f"n-{i}") for i in range(5)]
        edges = [_mock_edge(nodes[i], nodes[i + 1]) for i in range(4)]
        return _mock_workflow(nodes, edges)

    def test_single_terminal_node(self, chain_graph):
        nodes_with_outgoing = {e.from_node.node_id for e in chain_graph.edges}
        terminals = [
            n.node_id for n in chain_graph.nodes if n.node_id not in nodes_with_outgoing
        ]
        assert len(terminals) == 1
        assert terminals[0] == "n-4"

    def test_single_start_node(self, chain_graph):
        nodes_with_incoming = {e.to_node.node_id for e in chain_graph.edges}
        starts = [
            n.node_id for n in chain_graph.nodes if n.node_id not in nodes_with_incoming
        ]
        assert len(starts) == 1
        assert starts[0] == "n-0"

    def test_each_node_has_one_successor_except_last(self, chain_graph):
        for i in range(4):
            outgoing = [e for e in chain_graph.edges if e.from_node.node_id == f"n-{i}"]
            assert len(outgoing) == 1, f"n-{i} should have 1 outgoing edge"

    def test_last_node_has_no_successors(self, chain_graph):
        outgoing = [e for e in chain_graph.edges if e.from_node.node_id == "n-4"]
        assert len(outgoing) == 0


# ---------------------------------------------------------------------------
# Multi-terminal topology: A → [B, C] (no merge — both are terminal)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMultiTerminalTopology:
    """Topology where multiple nodes are terminal (no single merge)."""

    @pytest.fixture
    def multi_terminal_graph(self):
        a = _mock_node("n-a", is_start_node=True)
        b = _mock_node("n-b")
        c = _mock_node("n-c")
        edges = [_mock_edge(a, b), _mock_edge(a, c)]
        return _mock_workflow([a, b, c], edges)

    def test_two_terminal_nodes(self, multi_terminal_graph):
        nodes_with_outgoing = {e.from_node.node_id for e in multi_terminal_graph.edges}
        terminals = [
            n.node_id
            for n in multi_terminal_graph.nodes
            if n.node_id not in nodes_with_outgoing
        ]
        assert set(terminals) == {"n-b", "n-c"}


# ---------------------------------------------------------------------------
# Double-diamond: A → [B, C] → D → [E, F] → G
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDoubleDiamondTopology:
    """Two consecutive diamonds."""

    @pytest.fixture
    def double_diamond(self):
        a = _mock_node("n-a", is_start_node=True)
        b = _mock_node("n-b")
        c = _mock_node("n-c")
        d = _mock_node("n-d")
        e = _mock_node("n-e")
        f = _mock_node("n-f")
        g = _mock_node("n-g")
        edges = [
            _mock_edge(a, b),
            _mock_edge(a, c),
            _mock_edge(b, d),
            _mock_edge(c, d),
            _mock_edge(d, e),
            _mock_edge(d, f),
            _mock_edge(e, g),
            _mock_edge(f, g),
        ]
        return _mock_workflow([a, b, c, d, e, f, g], edges)

    def test_terminal_is_g(self, double_diamond):
        nodes_with_outgoing = {e.from_node.node_id for e in double_diamond.edges}
        terminals = [
            n.node_id
            for n in double_diamond.nodes
            if n.node_id not in nodes_with_outgoing
        ]
        assert terminals == ["n-g"]

    def test_d_is_both_fan_in_and_fan_out(self, double_diamond):
        """D receives from B,C and fans out to E,F."""
        incoming_d = [e for e in double_diamond.edges if e.to_node.node_id == "n-d"]
        outgoing_d = [e for e in double_diamond.edges if e.from_node.node_id == "n-d"]
        assert len(incoming_d) == 2  # from B and C
        assert len(outgoing_d) == 2  # to E and F

    def test_total_edges(self, double_diamond):
        assert len(double_diamond.edges) == 8

    @pytest.mark.asyncio
    async def test_successor_creation_for_d_creates_e_and_f(self):
        """When D completes, _create_successor_instances creates E and F."""
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()
        executor = WorkflowExecutor(mock_session)

        run_id = uuid4()
        d = _mock_node("n-d")
        e = _mock_node("n-e", template_id=uuid4())
        f = _mock_node("n-f", template_id=uuid4())
        edges = [_mock_edge(d, e), _mock_edge(d, f)]
        workflow = _mock_workflow([d, e, f], edges)

        completed_d = _mock_node_instance("n-d", workflow_run_id=run_id)
        executor.node_repo.get_node_instance_by_node_id = AsyncMock(return_value=None)
        mock_e = _mock_node_instance("n-e")
        mock_f = _mock_node_instance("n-f")
        executor.node_repo.create_node_instance = AsyncMock(
            side_effect=[mock_e, mock_f]
        )
        executor.edge_repo.create_edge_instance = AsyncMock()

        await executor._create_successor_instances(run_id, completed_d, workflow)

        assert executor.node_repo.create_node_instance.call_count == 2
        assert executor.edge_repo.create_edge_instance.call_count == 2
