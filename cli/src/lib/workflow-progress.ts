/**
 * Shared workflow run progress tracking.
 *
 * Used by both `workflows run` (submit + watch) and `workflow-runs watch` (attach).
 * Polls the status and graph endpoints, showing node completions as they happen.
 */

import chalk from 'chalk'

import type { ApiClient } from './api-client.js'
import { elapsed, sleep } from './cli-utils.js'

// -- Interfaces for API responses --

interface WorkflowRunStatus {
  workflow_run_id: string
  status: string
  started_at: string | null
  completed_at: string | null
  updated_at: string
}

interface GraphNode {
  node_instance_id: string
  node_id: string
  status: string
  started_at: string | null
  completed_at: string | null
  error_message: string | null
}

interface WorkflowRunGraph {
  workflow_run_id: string
  is_complete: boolean
  status: string | null
  summary: Record<string, number>
  nodes: GraphNode[]
}

interface WorkflowRunDetail {
  workflow_run_id: string
  workflow_name: string
  status: string
  started_at: string | null
  completed_at: string | null
  error_message: string | null
}

/**
 * Watches a workflow run in progress, printing live updates to the console.
 */
export class WorkflowProgressWatcher {
  private readonly client: ApiClient
  private readonly tenantId: string

  constructor(client: ApiClient, tenantId: string) {
    this.client = client
    this.tenantId = tenantId
  }

  /**
   * Get the current status of a workflow run (lightweight poll).
   */
  async getStatus(workflowRunId: string): Promise<WorkflowRunStatus | null> {
    return this.fetchSafe<WorkflowRunStatus>(
      `/workflow-runs/${encodeURIComponent(workflowRunId)}/status`,
    )
  }

  /**
   * Get full workflow run details.
   */
  async getDetail(workflowRunId: string): Promise<WorkflowRunDetail | null> {
    return this.fetchSafe<WorkflowRunDetail>(
      `/workflow-runs/${encodeURIComponent(workflowRunId)}`,
    )
  }

  /**
   * Main watch loop — polls status and graph, prints node completions.
   */
  async watch(workflowRunId: string): Promise<void> {
    const seenNodes = new Set<string>()
    const startTime = Date.now()
    let shownRunning = false

    const POLL_MS = 2000
    const TIMEOUT_MS = 10 * 60 * 1000 // 10 minutes

    while (Date.now() - startTime < TIMEOUT_MS) {
      const status = await this.getStatus(workflowRunId)

      if (!status) {
        await sleep(POLL_MS)
        continue
      }

      // Show the "running" transition once
      if (status.status === 'running' && !shownRunning) {
        const dur = elapsed(startTime)
        console.log(`  ${chalk.cyan('▸')} Executing nodes ${chalk.dim(`(${dur})`)}`)
        shownRunning = true
      }

      // Poll the graph for node completions while running
      if (status.status === 'running' || shownRunning) {
        await this.showNewNodes(workflowRunId, seenNodes)
      }

      // Terminal state
      if (status.status === 'completed' || status.status === 'failed' || status.status === 'cancelled') {
        // Show any remaining node completions
        await this.showNewNodes(workflowRunId, seenNodes)

        console.log()
        if (status.status === 'completed') {
          this.showSuccess(startTime)
        } else if (status.status === 'cancelled') {
          const dur = elapsed(startTime)
          console.log(`  ${chalk.yellow('⚠')} Workflow cancelled ${chalk.dim(`(${dur})`)}`)
        } else {
          await this.showFailure(workflowRunId, startTime)
        }

        console.log()
        return
      }

      await sleep(POLL_MS)
    }

    // Timeout
    console.log()
    console.log(chalk.yellow(`  ⚠ Timed out after ${elapsed(startTime)}. Workflow may still be running.`))
    console.log(chalk.dim(`  Check with: analysi workflow-runs status ${workflowRunId}`))
    console.log()
  }

  private async showNewNodes(workflowRunId: string, seenNodes: Set<string>): Promise<void> {
    const graph = await this.fetchSafe<WorkflowRunGraph>(
      `/workflow-runs/${encodeURIComponent(workflowRunId)}/graph`,
    )

    if (!graph || !Array.isArray(graph.nodes)) return

    for (const node of graph.nodes) {
      if (seenNodes.has(node.node_instance_id)) continue

      if (node.status === 'completed') {
        seenNodes.add(node.node_instance_id)
        const dur = this.nodeDuration(node)
        console.log(`    ${chalk.green('✓')} ${node.node_id} ${chalk.dim(dur)}`)
      } else if (node.status === 'failed') {
        seenNodes.add(node.node_instance_id)
        const errHint = node.error_message
          ? chalk.dim(` — ${node.error_message.split('\n')[0].slice(0, 80)}`)
          : ''
        console.log(`    ${chalk.red('✗')} ${node.node_id}${errHint}`)
      } else if (node.status === 'cancelled') {
        seenNodes.add(node.node_instance_id)
        console.log(`    ${chalk.yellow('–')} ${node.node_id} ${chalk.dim('(cancelled)')}`)
      }
    }
  }

  private showSuccess(startTime: number): void {
    const dur = elapsed(startTime)
    console.log(`  ${chalk.green('✓')} Workflow complete ${chalk.dim(`(${dur})`)}`)
  }

  private async showFailure(workflowRunId: string, startTime: number): Promise<void> {
    const dur = elapsed(startTime)
    console.log(`  ${chalk.red('✗')} Workflow failed ${chalk.dim(`(${dur})`)}`)

    const detail = await this.getDetail(workflowRunId)
    if (detail?.error_message) {
      const firstLine = detail.error_message.split('\n')[0]
      console.log(`    ${chalk.dim(firstLine.slice(0, 120))}`)
    }

    console.log(chalk.dim('\n  Use --output json for full error details'))
  }

  private nodeDuration(node: GraphNode): string {
    if (!node.started_at || !node.completed_at) return ''
    const start = new Date(node.started_at).getTime()
    const end = new Date(node.completed_at).getTime()
    const ms = end - start
    if (ms < 1000) return `${ms}ms`
    const secs = ms / 1000
    return `${secs.toFixed(1)}s`
  }

  private async fetchSafe<T>(
    path: string,
    query?: Record<string, string | number | boolean | undefined>,
  ): Promise<T | null> {
    try {
      const response = await this.client.request<T>('GET', path, this.tenantId, { query })
      return response.data
    } catch {
      return null
    }
  }
}
