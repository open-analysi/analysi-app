/**
 * Hand-written alert analysis command with live progress tracking.
 *
 * Default: submits analysis and shows a live progress view that polls the
 * analysis progress endpoint, showing pipeline steps and task completions
 * as they happen. Use --no-watch for fire-and-forget.
 */

import { Args, Flags } from '@oclif/core'
import chalk from 'chalk'

import { BaseCommand } from '../../base-command.js'
import { AnalysisProgressWatcher } from '../../lib/analysis-progress.js'
import { resolvePath } from '../../lib/config-loader.js'
import type { OutputFormat, PrintOptions } from '../../lib/output.js'
import { printResponse } from '../../lib/output.js'

interface AnalyzeResponse {
  analysis_id: string
  status: string
  message: string
}

export default class AlertsAnalyze extends BaseCommand {
  static override description = 'Analyze an alert with live progress tracking'

  static override examples = [
    '<%= config.bin %> alerts analyze <alert_id>',
    '<%= config.bin %> alerts analyze <alert_id> --no-watch',
  ]

  static override args = {
    alert_id: Args.string({
      description: 'Alert ID to analyze',
      required: true,
    }),
  }

  static override flags = {
    ...BaseCommand.baseFlags,
    watch: Flags.boolean({
      description: 'Watch analysis progress live (default: true)',
      default: true,
      allowNo: true,
    }),
  }

  async run(): Promise<void> {
    const { args, flags } = await this.parse(AlertsAnalyze)
    await this.initApi()

    const resolvedPath = resolvePath('/alerts/{alert_id}/analyze', args as Record<string, string>)

    // Submit the analysis
    const response = await this.client.request<AnalyzeResponse>(
      'POST',
      resolvedPath,
      this.tenantId,
    )

    const result = response.data

    // If --no-watch or non-table output, just print and exit
    if (!flags.watch || flags.output !== 'table') {
      const printOpts: PrintOptions = {
        format: flags.output as OutputFormat,
        fields: flags.fields ? (flags.fields as string).split(',').map((f) => f.trim()) : undefined,
        noHeader: flags['no-header'] as boolean,
      }

      printResponse(response, printOpts)
      return
    }

    // Start live progress view
    console.log()
    console.log(chalk.bold(`  Analyzing alert ${args.alert_id.slice(0, 8)}...`))
    console.log(chalk.dim(`  analysis: ${result.analysis_id}`))
    console.log()

    const watcher = new AnalysisProgressWatcher(this.client, this.tenantId)
    await watcher.watch(args.alert_id, result.analysis_id)
  }
}
