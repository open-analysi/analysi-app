/**
 * Shared analysis progress tracking.
 *
 * Used by both `alerts analyze` (submit + watch) and `alerts watch` (attach to running).
 * Polls the progress endpoint, shows pipeline steps, task completions, and final disposition.
 */

import chalk from 'chalk'

import type { ApiClient } from './api-client.js'
import { elapsed, formatDuration, sleep } from './cli-utils.js'

// -- Interfaces for API responses --

export interface ProgressData {
  analysis_id: string
  current_step: string | null
  completed_steps: number
  total_steps: number
  status: string
  error_message: string | null
  steps_detail: Record<string, StepDetail>
}

interface StepDetail {
  completed: boolean
  started_at: string | null
  completed_at: string | null
  retries: number
  error: string | null
}

interface TaskRunItem {
  id: string
  task_name: string
  status: string
  duration: string | null
  created_at: string
}

export interface AlertDetail {
  alert_id: string
  human_readable_id: string
  title: string
  analysis_status: string
  current_disposition_category: string | null
  current_disposition_display_name: string | null
  current_disposition_confidence: number | null
}

export interface AnalysisInfo {
  id: string
  status: string
  workflow_run_id?: string
  created_at: string
}

// Pipeline step display names
const STEP_LABELS: Record<string, string> = {
  pre_triage: 'Pre-triage',
  workflow_builder: 'Building workflow',
  workflow_execution: 'Executing tasks',
  final_disposition_update: 'Final disposition',
}

/**
 * Watches an analysis in progress, printing live updates to the console.
 * Returns when the analysis completes, fails, or times out.
 */
export class AnalysisProgressWatcher {
  private readonly client: ApiClient
  private readonly tenantId: string

  constructor(client: ApiClient, tenantId: string) {
    this.client = client
    this.tenantId = tenantId
  }

  /**
   * Find the latest analysis for an alert, or a specific one by ID.
   */
  async findAnalysis(alertId: string, analysisId?: string): Promise<AnalysisInfo | null> {
    const analyses = await this.fetchSafe<AnalysisInfo[]>(
      `/alerts/${encodeURIComponent(alertId)}/analyses`,
    )

    if (!Array.isArray(analyses) || analyses.length === 0) return null

    if (analysisId) {
      return analyses.find((a) => a.id === analysisId) ?? null
    }

    // Return the most recent (first in the list, API returns newest first)
    return analyses[0]
  }

  /**
   * Main watch loop — polls progress and prints live updates.
   */
  async watch(alertId: string, analysisId: string): Promise<void> {
    const seenTasks = new Set<string>()
    const startTime = Date.now()
    let lastStep = ''
    let workflowRunId: string | null = null

    const POLL_MS = 2000
    const TIMEOUT_MS = 10 * 60 * 1000 // 10 minutes

    while (Date.now() - startTime < TIMEOUT_MS) {
      const progress = await this.fetchSafe<ProgressData>(
        `/alerts/${encodeURIComponent(alertId)}/analysis/progress`,
      )

      if (!progress) {
        await sleep(POLL_MS)
        continue
      }

      // Show step transitions
      const currentStep = progress.current_step
      if (currentStep && currentStep !== lastStep) {
        const label = STEP_LABELS[currentStep] ?? currentStep
        const dur = elapsed(startTime)
        console.log(`  ${chalk.cyan('▸')} ${label} ${chalk.dim(`(${dur})`)}`)
        lastStep = currentStep
      }

      // During workflow_execution, show task completions
      if (currentStep === 'workflow_execution' || lastStep === 'workflow_execution') {
        if (!workflowRunId) {
          workflowRunId = await this.findWorkflowRunId(alertId, analysisId)
        }

        if (workflowRunId) {
          await this.showNewTasks(workflowRunId, seenTasks)
        }
      }

      // Terminal state
      if (progress.status === 'completed' || progress.status === 'failed') {
        console.log()
        if (progress.status === 'completed') {
          await this.showResult(alertId, startTime)
        } else {
          this.showFailure(progress, startTime)
        }

        console.log()
        return
      }

      await sleep(POLL_MS)
    }

    // Timeout
    console.log()
    console.log(chalk.yellow(`  ⚠ Timed out after ${elapsed(startTime)}. Analysis may still be running.`))
    console.log(chalk.dim(`  Check with: analysi alerts get ${alertId}`))
    console.log()
  }

  private async showNewTasks(workflowRunId: string, seenTasks: Set<string>): Promise<void> {
    const tasks = await this.fetchSafe<TaskRunItem[]>(
      '/task-runs',
      { workflow_run_id: workflowRunId, limit: 50 },
    )

    if (!Array.isArray(tasks)) return

    for (const task of tasks) {
      if (seenTasks.has(task.id)) continue

      if (task.status === 'completed') {
        seenTasks.add(task.id)
        const dur = formatDuration(task.duration)
        console.log(`    ${chalk.green('✓')} ${task.task_name} ${chalk.dim(dur)}`)
      } else if (task.status === 'failed') {
        seenTasks.add(task.id)
        console.log(`    ${chalk.red('✗')} ${task.task_name}`)
      }
    }
  }

  private async showResult(alertId: string, startTime: number): Promise<void> {
    const alert = await this.fetchSafe<AlertDetail>(
      `/alerts/${encodeURIComponent(alertId)}`,
    )

    const dur = elapsed(startTime)

    if (alert) {
      const disposition = alert.current_disposition_display_name ?? alert.current_disposition_category ?? 'Unknown'
      const confidence = alert.current_disposition_confidence
      const confStr = confidence ? chalk.dim(` (${confidence}% confidence)`) : ''

      console.log(`  ${chalk.green('✓')} Analysis complete ${chalk.dim(`(${dur})`)}`)
      console.log()
      console.log(`    ${chalk.bold('Disposition:')} ${colorDisposition(disposition)}${confStr}`)
    } else {
      console.log(`  ${chalk.green('✓')} Analysis complete ${chalk.dim(`(${dur})`)}`)
    }
  }

  private showFailure(progress: ProgressData, startTime: number): void {
    const dur = elapsed(startTime)
    console.log(`  ${chalk.red('✗')} Analysis failed ${chalk.dim(`(${dur})`)}`)
    if (progress.error_message) {
      // eslint-disable-next-line no-control-regex
      const clean = progress.error_message.replace(/\u001B\[\d+(?:;\d+)*m/g, '')
      const firstLine = clean.split('\n')[0]
      console.log(`    ${chalk.dim(firstLine.slice(0, 120))}`)
    }

    console.log(chalk.dim('\n  Use --output json for full error details'))
  }

  private async findWorkflowRunId(alertId: string, analysisId: string): Promise<string | null> {
    const analysis = await this.findAnalysis(alertId, analysisId)
    return analysis?.workflow_run_id ?? null
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

export function colorDisposition(disposition: string): string {
  const lower = disposition.toLowerCase()
  if (lower.includes('true positive') || lower.includes('malicious') || lower.includes('compromise')) {
    return chalk.red(disposition)
  }

  if (lower.includes('false positive') || lower.includes('benign')) {
    return chalk.green(disposition)
  }

  return chalk.yellow(disposition)
}
