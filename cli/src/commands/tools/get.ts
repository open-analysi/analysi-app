/**
 * Hand-written tools get command.
 *
 * Fetches detailed information for specific Cy tools by their FQNs.
 * Accepts multiple FQNs as variadic arguments.
 *
 * The /integrations/tools/all endpoint returns tools as an array of
 * objects with {fqn, name, description, params_schema, ...}. We build
 * a map keyed by FQN for efficient lookup.
 */

import { Args, Flags } from '@oclif/core'
import chalk from 'chalk'

import { BaseCommand } from '../../base-command.js'
import type { OutputFormat, PrintOptions } from '../../lib/output.js'
import { printResponse } from '../../lib/output.js'

interface ToolItem {
  fqn: string
  name: string
  description: string
  category: string
  integration_id: string | null
  params_schema: Record<string, unknown>
}

interface ToolsAllResponse {
  tools: ToolItem[]
  total: number
}

export default class ToolsGet extends BaseCommand {
  static override description = 'Get detailed information for Cy tools by FQN'

  static override examples = [
    '<%= config.bin %> tools get native::llm::llm_run',
    '<%= config.bin %> tools get app::virustotal::ip_reputation app::splunk::spl_run',
    '<%= config.bin %> tools get sum len --output json',
  ]

  // Strict false to allow multiple variadic args
  static override strict = false

  static override args = {
    fqns: Args.string({
      description: 'One or more tool FQNs (e.g. native::llm::llm_run, app::virustotal::ip_reputation)',
      required: true,
    }),
  }

  static override flags = {
    ...BaseCommand.baseFlags,
  }

  async run(): Promise<void> {
    const { argv, flags } = await this.parse(ToolsGet)
    await this.initApi()

    const fqns = argv as string[]

    if (fqns.length === 0) {
      this.error('Provide at least one tool FQN. Use `analysi tools list` to discover tools.')
    }

    // Fetch all tools (the REST API returns an array)
    const response = await this.client.request<ToolsAllResponse>(
      'GET',
      '/integrations/tools/all',
      this.tenantId,
    )

    // Build a map keyed by FQN for efficient lookup
    const toolsArray = response.data.tools ?? []
    const toolsByFqn = new Map<string, ToolItem>()
    for (const tool of toolsArray) {
      toolsByFqn.set(tool.fqn, tool)
    }

    // Filter to requested FQNs
    const matched: ToolItem[] = []
    const notFound: string[] = []
    for (const fqn of fqns) {
      const tool = toolsByFqn.get(fqn)
      if (tool) {
        matched.push(tool)
      } else {
        notFound.push(fqn)
      }
    }

    // For non-table output, print matched tools as array
    if (flags.output !== 'table') {
      const printOpts: PrintOptions = {
        format: flags.output as OutputFormat,
        fields: flags.fields ? (flags.fields as string).split(',').map((f) => f.trim()) : undefined,
        noHeader: flags['no-header'] as boolean,
      }

      printResponse(
        { data: matched, meta: response.meta },
        printOpts,
      )
      return
    }

    // Pretty-print tool details
    console.log()
    for (const tool of matched) {
      console.log(`  ${chalk.bold.cyan(tool.fqn)}`)
      if (tool.description) console.log(`  ${tool.description}`)
      if (tool.category) console.log(chalk.dim(`  category: ${tool.category}`))
      if (tool.integration_id) console.log(chalk.dim(`  integration: ${tool.integration_id}`))
      console.log()

      const paramsSchema = tool.params_schema ?? {}
      const properties = (paramsSchema.properties ?? {}) as Record<string, Record<string, unknown>>
      const required = (paramsSchema.required ?? []) as string[]

      const paramEntries = Object.entries(properties)
      if (paramEntries.length > 0) {
        console.log(chalk.dim('  Parameters:'))
        for (const [name, spec] of paramEntries) {
          const reqTag = required.includes(name) ? chalk.red(' *') : ''
          const type = (spec.type as string) ?? 'string'
          const pDesc = (spec.description as string) ?? ''
          console.log(`    ${chalk.white(name)}${reqTag}  ${chalk.dim(type)}  ${chalk.dim(pDesc)}`)
        }

        console.log()
      }
    }

    if (notFound.length > 0) {
      console.log(chalk.yellow(`  Not found: ${notFound.join(', ')}`))
      console.log(chalk.dim('  Use `analysi tools list` to see available tools.'))
      console.log()
    }
  }
}
