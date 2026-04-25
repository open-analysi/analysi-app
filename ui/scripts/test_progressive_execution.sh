#!/bin/bash

# Test progressive workflow execution
WORKFLOW_ID="63891782-32a2-45aa-9cad-57e0a2530f4e"
BASE_URL="http://localhost:8001/v1/default"

echo "=== Starting workflow execution ==="
RESPONSE=$(curl -s -X POST "${BASE_URL}/workflows/${WORKFLOW_ID}/run" \
  -H "Content-Type: application/json" \
  -d '{"input_data": {"ip": "1.1.1.1", "context": "progressive_execution_test"}}')

WORKFLOW_RUN_ID=$(echo "$RESPONSE" | jq -r '.data.workflow_run_id')
echo "Started workflow run: $WORKFLOW_RUN_ID"

echo ""
echo "=== Polling execution states ==="

# Monitor execution with rapid polling
for i in {1..20}; do
  echo "--- Poll $i ($(date)) ---"

  # Get current graph state (Sifnos envelope: {data, meta})
  GRAPH=$(curl -s "${BASE_URL}/workflow-runs/${WORKFLOW_RUN_ID}/graph" | jq '.data')

  echo "Is complete: $(echo "$GRAPH" | jq -r '.is_complete')"
  echo "Summary: $(echo "$GRAPH" | jq -c '.summary')"

  NODE_COUNT=$(echo "$GRAPH" | jq '.nodes | length')
  echo "Node count: $NODE_COUNT"

  if [ "$NODE_COUNT" -gt 0 ]; then
    echo "Nodes:"
    echo "$GRAPH" | jq -r '.nodes[] | "  " + .node_id + ": " + .status + " (" + (.started_at // "not started") + " -> " + (.ended_at // "running") + ")"'
  else
    echo "No nodes created yet"
  fi

  IS_COMPLETE=$(echo "$GRAPH" | jq -r '.is_complete')
  if [ "$IS_COMPLETE" = "true" ] && [ "$NODE_COUNT" -gt 0 ]; then
    echo "Execution completed!"
    break
  fi

  sleep 1
done

echo ""
echo "=== Final execution graph ==="
FINAL_GRAPH=$(curl -s "${BASE_URL}/workflow-runs/${WORKFLOW_RUN_ID}/graph" | jq '.data')
echo "$FINAL_GRAPH" | jq '{
  workflow_run_id,
  is_complete,
  summary,
  nodes: [.nodes[] | {
    node_id,
    status,
    started_at,
    ended_at,
    input_data,
    output_sample: (.output_data.result.ip_address // .output_data.ip // "no output")
  }]
}'

echo ""
echo "=== Status endpoint ==="
curl -s "${BASE_URL}/workflow-runs/${WORKFLOW_RUN_ID}/status" | jq '.data'