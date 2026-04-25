/**
 * Hand-written skill tree command.
 *
 * Extracts the `files` array from the tree response and renders it
 * as a table instead of a collapsed single-object view.
 */

import { Args } from '@oclif/core'

import { BaseCommand } from '../../base-command.js'
import { resolvePath } from '../../lib/config-loader.js'
import type { OutputFormat, PrintOptions } from '../../lib/output.js'
import { printResponse } from '../../lib/output.js'

interface TreeFile {
  path: string
  document_id: string
  staged: boolean
}

interface TreeResponse {
  skill_id: string
  files: TreeFile[]
  total: number
}

export default class SkillsTree extends BaseCommand {
  static override description = 'Get the file tree for a skill'

  static override examples = [
    '<%= config.bin %> skills tree <id>',
    '<%= config.bin %> skills tree <id> --output json',
  ]

  static override args = {
    id: Args.string({
      description: 'Skill ID',
      required: true,
    }),
  }

  static override flags = {
    ...BaseCommand.baseFlags,
  }

  async run(): Promise<void> {
    const { args, flags } = await this.parse(SkillsTree)
    await this.initApi()

    const resolvedPath = resolvePath('/skills/{id}/tree', args as Record<string, string>)
    const response = await this.client.request<TreeResponse>('GET', resolvedPath, this.tenantId)

    const printOpts: PrintOptions = {
      format: flags.output as OutputFormat,
      fields: flags.fields ? (flags.fields as string).split(',').map((f) => f.trim()) : undefined,
      noHeader: flags['no-header'] as boolean,
    }

    // Render the files array as a table instead of the wrapper object
    printResponse({ data: response.data.files, meta: response.meta }, printOpts)
  }
}
