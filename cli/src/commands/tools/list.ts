/**
 * Hand-written tools list command.
 *
 * The /integrations/tools/all endpoint returns {tools: [...], total: N}.
 * We unwrap the tools array so table mode shows one row per tool.
 */

import { Flags } from '@oclif/core'

import { BaseCommand } from '../../base-command.js'
import type { OutputFormat, PrintOptions } from '../../lib/output.js'
import { printResponse } from '../../lib/output.js'

interface ToolItem {
  fqn: string
  name: string
  description: string
  category: string
  integration_id: string | null
}

interface ToolsAllResponse {
  tools: ToolItem[]
  total: number
}

export default class ToolsList extends BaseCommand {
  static override description = 'List all active Cy tool FQNs (native + integration tools)'

  static override examples = [
    '<%= config.bin %> tools list',
    '<%= config.bin %> tools list --output json',
    '<%= config.bin %> tools list --fields fqn,category --output csv --no-header',
  ]

  static override flags = {
    ...BaseCommand.baseFlags,
  }

  async run(): Promise<void> {
    const { flags } = await this.parse(ToolsList)
    await this.initApi()

    const response = await this.client.request<ToolsAllResponse>(
      'GET',
      '/integrations/tools/all',
      this.tenantId,
    )

    // Unwrap: pass the tools array as data so table mode renders rows
    const printOpts: PrintOptions = {
      format: flags.output as OutputFormat,
      fields: flags.fields ? (flags.fields as string).split(',').map((f) => f.trim()) : undefined,
      noHeader: flags['no-header'] as boolean,
    }

    printResponse(
      { data: response.data.tools, meta: { ...response.meta, total: response.data.total } },
      printOpts,
    )
  }
}
