/**
 * Hand-written command to attach to an already-running alert analysis.
 *
 * Finds the latest analysis for the given alert and shows live progress.
 * Useful when the analysis was started via the API, another session, or
 * you want to re-attach after disconnecting.
 */

import { Args } from '@oclif/core'
import chalk from 'chalk'

import { BaseCommand } from '../../base-command.js'
import { AnalysisProgressWatcher, colorDisposition } from '../../lib/analysis-progress.js'

export default class AlertsWatch extends BaseCommand {
  static override description = 'Watch a running alert analysis'

  static override examples = [
    '<%= config.bin %> alerts watch <alert_id>',
  ]

  static override args = {
    alert_id: Args.string({
      description: 'Alert ID to watch',
      required: true,
    }),
  }

  static override flags = {
    ...BaseCommand.baseFlags,
  }

  async run(): Promise<void> {
    const { args } = await this.parse(AlertsWatch)
    await this.initApi()

    const watcher = new AnalysisProgressWatcher(this.client, this.tenantId)

    // Find the latest analysis for this alert
    const analysis = await watcher.findAnalysis(args.alert_id)

    if (!analysis) {
      console.log()
      console.log(chalk.yellow(`  No analyses found for alert ${args.alert_id.slice(0, 8)}...`))
      console.log(chalk.dim(`  Start one with: analysi alerts analyze ${args.alert_id}`))
      console.log()
      return
    }

    // If already completed, show the result directly
    if (analysis.status === 'completed') {
      const alert = await this.fetchAlert(args.alert_id)

      console.log()
      console.log(chalk.bold(`  Alert ${args.alert_id.slice(0, 8)}...`))
      console.log(chalk.dim(`  analysis: ${analysis.id}`))
      console.log()

      if (alert) {
        const disposition = alert.current_disposition_display_name ?? alert.current_disposition_category ?? 'Unknown'
        const confidence = alert.current_disposition_confidence
        const confStr = confidence ? chalk.dim(` (${confidence}% confidence)`) : ''
        console.log(`  ${chalk.green('✓')} Analysis already complete`)
        console.log()
        console.log(`    ${chalk.bold('Disposition:')} ${colorDisposition(disposition)}${confStr}`)
      } else {
        console.log(`  ${chalk.green('✓')} Analysis already complete`)
      }

      console.log()
      return
    }

    if (analysis.status === 'failed') {
      console.log()
      console.log(chalk.bold(`  Alert ${args.alert_id.slice(0, 8)}...`))
      console.log(chalk.dim(`  analysis: ${analysis.id}`))
      console.log()
      console.log(`  ${chalk.red('✗')} Analysis already failed`)
      console.log(chalk.dim(`  Re-run with: analysi alerts analyze ${args.alert_id}`))
      console.log()
      return
    }

    // Analysis is in progress — attach and watch
    console.log()
    console.log(chalk.bold(`  Watching alert ${args.alert_id.slice(0, 8)}...`))
    console.log(chalk.dim(`  analysis: ${analysis.id} (${analysis.status})`))
    console.log()

    await watcher.watch(args.alert_id, analysis.id)
  }

  private async fetchAlert(alertId: string): Promise<{
    current_disposition_display_name: string | null
    current_disposition_category: string | null
    current_disposition_confidence: number | null
  } | null> {
    try {
      const response = await this.client.request<{
        current_disposition_display_name: string | null
        current_disposition_category: string | null
        current_disposition_confidence: number | null
      }>('GET', `/alerts/${encodeURIComponent(alertId)}`, this.tenantId)
      return response.data
    } catch {
      return null
    }
  }
}
