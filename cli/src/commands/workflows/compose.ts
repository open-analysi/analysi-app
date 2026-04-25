/**
 * Hand-written workflow compose command.
 *
 * Creates a workflow from the array-based composition format.
 * The composition format uses task cy_names and supports parallel branches.
 */

import { Flags } from '@oclif/core'
import chalk from 'chalk'

import { BaseCommand } from '../../base-command.js'
import { parseDataFlag } from '../../lib/data-reader.js'
import type { OutputFormat, PrintOptions } from '../../lib/output.js'
import { printResponse } from '../../lib/output.js'

interface ComposeResponse {
  status: string // "success", "needs_decision", or "error"
  workflow_id: string | null
  errors: Array<{ message: string }>
  warnings: Array<{ message: string }>
  questions: Array<{ message: string }>
  plan: Record<string, unknown> | null
}

export default class WorkflowsCompose extends BaseCommand {
  static override description = 'Compose a workflow from array-based composition format'

  static override examples = [
    '<%= config.bin %> workflows compose --data @composition.json',
    '<%= config.bin %> workflows compose --name "Triage Pipeline" --data \'{"composition": ["identity", "enrich_ip", "triage"]}\'',
  ]

  static override flags = {
    ...BaseCommand.baseFlags,
    data: Flags.string({
      description: 'Composition JSON (or @filepath). Must include: composition (array), name, description',
      required: true,
    }),
    name: Flags.string({
      description: 'Workflow name (overrides name in JSON data)',
    }),
    description: Flags.string({
      description: 'Workflow description (overrides description in JSON data)',
    }),
    execute: Flags.boolean({
      description: 'Execute the workflow immediately after composition',
      default: false,
    }),
  }

  async run(): Promise<void> {
    const { flags } = await this.parse(WorkflowsCompose)
    await this.initApi()

    const data = parseDataFlag(flags.data as string) as Record<string, unknown>

    // Build the compose request body
    const body: Record<string, unknown> = {
      composition: data.composition ?? data,
      name: flags.name ?? data.name ?? 'Unnamed Workflow',
      description: flags.description ?? data.description ?? '',
      execute: flags.execute,
    }

    if (data.data_samples) body.data_samples = data.data_samples

    const response = await this.client.request<ComposeResponse>(
      'POST',
      '/workflows/compose',
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
      if (result.status === 'error') this.exit(1)
      return
    }

    // Pretty-print composition results using API's status field
    console.log()
    if (result.status === 'success') {
      if (result.workflow_id) {
        console.log(`  ${chalk.green('✓')} Workflow created: ${result.workflow_id}`)
      } else {
        console.log(`  ${chalk.green('✓')} Composition plan ready`)
      }
    } else if (result.status === 'needs_decision') {
      console.log(`  ${chalk.yellow('?')} Composition needs decisions`)
    } else {
      console.log(`  ${chalk.red('✗')} Composition failed`)
    }

    if (result.errors?.length > 0) {
      console.log()
      console.log(chalk.red.bold('  Errors:'))
      for (const err of result.errors) {
        console.log(`    ${chalk.red('•')} ${err.message}`)
      }
    }

    if (result.warnings?.length > 0) {
      console.log()
      console.log(chalk.yellow.bold('  Warnings:'))
      for (const warn of result.warnings) {
        console.log(`    ${chalk.yellow('•')} ${warn.message}`)
      }
    }

    if (result.questions?.length > 0) {
      console.log()
      console.log(chalk.cyan.bold('  Questions:'))
      for (const q of result.questions) {
        console.log(`    ${chalk.cyan('?')} ${q.message}`)
      }
    }

    if (result.plan) {
      console.log(chalk.dim(`\n  Use --output json to see full plan details`))
    }

    console.log()

    if (result.status === 'error') this.exit(1)
  }
}
