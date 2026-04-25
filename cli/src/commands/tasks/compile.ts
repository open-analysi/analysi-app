/**
 * Hand-written task compile command.
 *
 * Analyzes a Cy script — reports tools used, external variables,
 * and any errors without executing it.
 */

import { Args, Flags } from '@oclif/core'
import chalk from 'chalk'

import { BaseCommand } from '../../base-command.js'
import { readScriptFlag } from '../../lib/script-reader.js'
import type { OutputFormat, PrintOptions } from '../../lib/output.js'
import { printResponse } from '../../lib/output.js'

interface AnalyzeResponse {
  task_id: string | null
  cy_name: string | null
  tools_used: string[] | null
  external_variables: string[] | null
  errors: string[] | null
}

export default class TasksCompile extends BaseCommand {
  static override description = 'Compile and type-check a Cy script without executing'

  static override examples = [
    '<%= config.bin %> tasks compile @enrich_ip.cy',
    '<%= config.bin %> tasks compile \'result = sum([1, 2, 3])\'',
    '<%= config.bin %> tasks compile @script.cy --output json',
  ]

  static override args = {
    script: Args.string({
      description: 'Cy script content (or @filepath to read from .cy file)',
      required: true,
    }),
  }

  static override flags = {
    ...BaseCommand.baseFlags,
  }

  async run(): Promise<void> {
    const { args, flags } = await this.parse(TasksCompile)
    await this.initApi()

    const script = readScriptFlag(args.script)

    const response = await this.client.request<AnalyzeResponse>(
      'POST',
      '/tasks/analyze',
      this.tenantId,
      { body: { script } },
    )

    const result = response.data

    // For non-table output, just print the raw response
    if (flags.output !== 'table') {
      const printOpts: PrintOptions = {
        format: flags.output as OutputFormat,
        fields: flags.fields ? (flags.fields as string).split(',').map((f) => f.trim()) : undefined,
        noHeader: flags['no-header'] as boolean,
      }

      printResponse(response, printOpts)
      if (result.errors && result.errors.length > 0) this.exit(1)
      return
    }

    // Table output: pretty-print analysis results
    console.log()
    const hasErrors = result.errors && result.errors.length > 0
    if (hasErrors) {
      console.log(`  ${chalk.red('✗')} Compilation failed`)
    } else {
      console.log(`  ${chalk.green('✓')} Compilation successful`)
    }

    if (result.tools_used && result.tools_used.length > 0) {
      console.log(chalk.dim(`  Tools: ${result.tools_used.join(', ')}`))
    }

    if (result.external_variables && result.external_variables.length > 0) {
      console.log(chalk.dim(`  External variables: ${result.external_variables.join(', ')}`))
    }

    if (hasErrors) {
      console.log()
      console.log(chalk.red.bold('  Errors:'))
      for (const err of result.errors!) {
        console.log(`    ${chalk.red('•')} ${err}`)
      }
    }

    console.log()

    if (hasErrors) this.exit(1)
  }
}
