/**
 * Hand-written integration tool execution command.
 *
 * Executes an integration tool (action) and returns results.
 * Useful for testing integration actions before writing Cy scripts.
 */

import { Args, Flags } from '@oclif/core'
import chalk from 'chalk'

import { BaseCommand } from '../../base-command.js'
import { parseDataFlag } from '../../lib/data-reader.js'
import type { OutputFormat, PrintOptions } from '../../lib/output.js'
import { printResponse } from '../../lib/output.js'

interface RunToolResponse {
  status: string
  output: unknown
  output_schema?: unknown
  error?: string
  execution_time_ms?: number
}

export default class IntegrationsRunTool extends BaseCommand {
  static override description = 'Execute an integration tool and return results'

  static override examples = [
    '<%= config.bin %> integrations run-tool splunk-prod health_check',
    '<%= config.bin %> integrations run-tool virustotal-main ip_reputation --args \'{"ip": "8.8.8.8"}\'',
    '<%= config.bin %> integrations run-tool echo-edr-1 get_alerts --args @args.json --capture-schema',
  ]

  static override args = {
    integration_id: Args.string({
      description: 'Integration INSTANCE ID (e.g. splunk-prod, virustotal-main)',
      required: true,
    }),
    action_id: Args.string({
      description: 'Action identifier (e.g. ip_reputation, health_check)',
      required: true,
    }),
  }

  static override flags = {
    ...BaseCommand.baseFlags,
    args: Flags.string({
      description: 'Tool arguments as JSON (or @filepath)',
      default: '{}',
    }),
    'capture-schema': Flags.boolean({
      description: 'Capture JSON schema of tool output',
      default: false,
    }),
    timeout: Flags.integer({
      description: 'Execution timeout in seconds',
      default: 30,
    }),
  }

  async run(): Promise<void> {
    const { args, flags } = await this.parse(IntegrationsRunTool)
    await this.initApi()

    const toolArgs = parseDataFlag(flags.args as string) as Record<string, unknown>

    const body = {
      arguments: toolArgs,
      capture_schema: flags['capture-schema'],
      timeout_seconds: flags.timeout,
    }

    const intId = encodeURIComponent(args.integration_id)
    const actId = encodeURIComponent(args.action_id)

    const response = await this.client.request<RunToolResponse>(
      'POST',
      `/integrations/${intId}/tools/${actId}/execute`,
      this.tenantId,
      { body },
    )

    const result = response.data

    // For non-table output, print raw
    if (flags.output !== 'table') {
      const printOpts: PrintOptions = {
        format: flags.output as OutputFormat,
        fields: flags.fields ? (flags.fields as string).split(',').map((f) => f.trim()) : undefined,
        noHeader: flags['no-header'] as boolean,
      }

      printResponse(response, printOpts)
      if (result.status !== 'success') this.exit(1)
      return
    }

    // Pretty-print execution results
    let failed = false
    console.log()
    if (result.status === 'success') {
      console.log(`  ${chalk.green('✓')} ${args.integration_id}::${args.action_id}`)
      if (result.execution_time_ms !== undefined) {
        console.log(chalk.dim(`  ${result.execution_time_ms}ms`))
      }

      console.log()
      if (result.output !== null && result.output !== undefined) {
        const outputStr = JSON.stringify(result.output, null, 2)
        // Indent each line of the output
        for (const line of outputStr.split('\n')) {
          console.log(`  ${line}`)
        }
      }
    } else {
      console.log(`  ${chalk.red('✗')} ${args.integration_id}::${args.action_id} — ${result.status}`)
      if (result.error) {
        console.log(`    ${chalk.dim(result.error)}`)
      }
      failed = true
    }

    if (result.output_schema) {
      console.log()
      console.log(chalk.bold('  Output Schema:'))
      const schemaStr = JSON.stringify(result.output_schema, null, 2)
      for (const line of schemaStr.split('\n')) {
        console.log(`  ${line}`)
      }
    }

    console.log()

    if (failed) this.exit(1)
  }
}
