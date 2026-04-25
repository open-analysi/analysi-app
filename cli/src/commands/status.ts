/**
 * Hand-written status dashboard command.
 * Shows a quick overview of the platform: alerts, recent runs, integration health.
 */

import { Flags } from '@oclif/core'
import chalk from 'chalk'

import { BaseCommand } from '../base-command.js'
import type { ApiResponse } from '../lib/types.js'

interface AlertItem {
  alert_id: string
  title: string
  severity: string
  analysis_status: string
}

interface RunItem {
  id: string
  task_name?: string
  workflow_name?: string
  status: string
  created_at: string
  duration?: string
}

interface IntegrationItem {
  integration_id: string
  name: string
  enabled: boolean
  health?: {
    status: string
    message?: string
    recent_failure_rate?: number
  }
}

export default class Status extends BaseCommand {
  static override description = 'Platform status dashboard — alerts, runs, integration health'

  static override examples = [
    '<%= config.bin %> status',
  ]

  static override flags = {
    ...BaseCommand.baseFlags,
  }

  async run(): Promise<void> {
    await this.initApi()
    const { flags } = await this.parse(Status)

    if (flags.output === 'json') {
      await this.jsonDashboard()
      return
    }

    // Fetch all data in parallel
    const [alerts, taskRuns, workflowRuns, integrations] = await Promise.all([
      this.fetchSafe<AlertItem[]>('/alerts', { limit: 100 }),
      this.fetchSafe<RunItem[]>('/task-runs', { limit: 50 }),
      this.fetchSafe<RunItem[]>('/workflow-runs', { limit: 50 }),
      this.fetchSafe<IntegrationItem[]>('/integrations'),
    ])

    console.log()
    console.log(chalk.bold('  Analysi Platform Status'))
    console.log(chalk.dim('  ─'.repeat(30)))

    // Alerts summary
    this.printAlertsSummary(alerts)

    // Task runs summary
    this.printRunsSummary('Task Runs', taskRuns)

    // Workflow runs summary
    this.printRunsSummary('Workflow Runs', workflowRuns)

    // Integration health
    this.printIntegrationHealth(integrations)

    console.log()
  }

  private async fetchSafe<T>(
    path: string,
    query?: Record<string, string | number | boolean | undefined>,
  ): Promise<T> {
    try {
      const response = await this.client.request<T>(
        'GET',
        path,
        this.tenantId,
        { query },
      )

      return response.data
    } catch {
      return [] as unknown as T
    }
  }

  private async jsonDashboard(): Promise<void> {
    const [alerts, taskRuns, workflowRuns, integrations] = await Promise.all([
      this.fetchSafe<AlertItem[]>('/alerts', { limit: 100 }),
      this.fetchSafe<RunItem[]>('/task-runs', { limit: 50 }),
      this.fetchSafe<RunItem[]>('/workflow-runs', { limit: 50 }),
      this.fetchSafe<IntegrationItem[]>('/integrations'),
    ])

    const alertArr = Array.isArray(alerts) ? alerts : []
    const taskArr = Array.isArray(taskRuns) ? taskRuns : []
    const wfArr = Array.isArray(workflowRuns) ? workflowRuns : []
    const intArr = Array.isArray(integrations) ? integrations : []

    const summary = {
      alerts: {
        total: alertArr.length,
        by_status: countBy(alertArr, 'analysis_status'),
        by_severity: countBy(alertArr, 'severity'),
      },
      task_runs: {
        total: taskArr.length,
        by_status: countBy(taskArr, 'status'),
      },
      workflow_runs: {
        total: wfArr.length,
        by_status: countBy(wfArr, 'status'),
      },
      integrations: intArr.map((i) => ({
        id: i.integration_id,
        name: i.name,
        enabled: i.enabled,
        health: i.health?.status ?? 'unknown',
      })),
    }

    console.log(JSON.stringify(summary, null, 2))
  }

  private printAlertsSummary(alerts: AlertItem[] | unknown): void {
    const items = Array.isArray(alerts) ? alerts : []
    console.log()
    console.log(chalk.bold('  📋 Alerts'))

    if (items.length === 0) {
      console.log(chalk.dim('     No alerts'))
      return
    }

    const byStatus = countBy(items, 'analysis_status')
    const bySeverity = countBy(items, 'severity')

    const statusParts = Object.entries(byStatus)
      .map(([status, count]) => {
        const color = status === 'completed' ? chalk.green : status === 'analyzing' ? chalk.yellow : chalk.white
        return `${color(String(count))} ${status}`
      })
      .join('  ')

    const severityParts = Object.entries(bySeverity)
      .sort(([a], [b]) => severityOrder(a) - severityOrder(b))
      .map(([sev, count]) => `${severityColor(sev)(String(count))} ${sev}`)
      .join('  ')

    console.log(`     ${chalk.dim('Status:')}   ${statusParts}`)
    console.log(`     ${chalk.dim('Severity:')} ${severityParts}`)
  }

  private printRunsSummary(label: string, runs: RunItem[] | unknown): void {
    const items = Array.isArray(runs) ? runs : []
    console.log()
    console.log(chalk.bold(`  ⚡ ${label}`))

    if (items.length === 0) {
      console.log(chalk.dim('     No recent runs'))
      return
    }

    const byStatus = countBy(items, 'status')
    const parts = Object.entries(byStatus)
      .map(([status, count]) => {
        const color = status === 'completed' ? chalk.green
          : status === 'failed' ? chalk.red
            : status === 'running' ? chalk.yellow
              : chalk.white
        return `${color(String(count))} ${status}`
      })
      .join('  ')

    console.log(`     ${parts}`)

    // Show any currently running
    const running = items.filter((r) => r.status === 'running')
    if (running.length > 0) {
      for (const r of running.slice(0, 3)) {
        const name = r.task_name ?? r.workflow_name ?? r.id.slice(0, 8)
        console.log(chalk.yellow(`     → ${name}`))
      }
    }

    // Show any recently failed
    const failed = items.filter((r) => r.status === 'failed')
    if (failed.length > 0) {
      for (const r of failed.slice(0, 3)) {
        const name = r.task_name ?? r.workflow_name ?? r.id.slice(0, 8)
        console.log(chalk.red(`     ✗ ${name}`))
      }
    }
  }

  private printIntegrationHealth(integrations: IntegrationItem[] | unknown): void {
    const items = Array.isArray(integrations) ? integrations : []
    console.log()
    console.log(chalk.bold('  🔌 Integrations'))

    if (items.length === 0) {
      console.log(chalk.dim('     No integrations configured'))
      return
    }

    for (const integ of items) {
      const healthStatus = integ.health?.status ?? 'unknown'
      const icon = healthStatus === 'healthy' ? chalk.green('●')
        : healthStatus === 'unhealthy' ? chalk.red('●')
          : chalk.yellow('●')

      const enabledTag = integ.enabled ? '' : chalk.dim(' (disabled)')
      const msg = integ.health?.message ? chalk.dim(` — ${integ.health.message}`) : ''
      console.log(`     ${icon} ${integ.name}${enabledTag}${msg}`)
    }
  }
}

function countBy<T>(
  items: T[],
  key: keyof T,
): Record<string, number> {
  const counts: Record<string, number> = {}
  for (const item of items) {
    const value = String(item[key] ?? 'unknown')
    counts[value] = (counts[value] ?? 0) + 1
  }

  return counts
}

function severityOrder(sev: string): number {
  const order: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3, informational: 4 }
  return order[sev] ?? 5
}

function severityColor(sev: string): (s: string) => string {
  switch (sev) {
    case 'critical': return chalk.red.bold
    case 'high': return chalk.red
    case 'medium': return chalk.yellow
    case 'low': return chalk.blue
    default: return chalk.dim
  }
}
