/**
 * AUTO-GENERATED — DO NOT EDIT
 * Generated from cli-config.yaml by: npm run generate
 */

import { Args, Flags } from '@oclif/core'
import { BaseCommand } from '../../base-command.js'
import { resolvePath } from '../../lib/config-loader.js'

export default class KnowledgeUnitsGetDocument extends BaseCommand {
  static override description = 'Get a document knowledge unit'

  static override examples = [
    '<%= config.bin %> knowledge-units get-document <id>',
  ]

  static override args = {
    id: Args.string({
      description: 'Document KU ID',
      required: true,
    })
  }
  static override flags = {
    ...BaseCommand.baseFlags,
  }

  async run(): Promise<void> {
    const { args, flags } = await this.parse(KnowledgeUnitsGetDocument)
    await this.initApi()
    const resolvedPath = resolvePath('/knowledge-units/documents/{id}', args as Record<string, string>)

    await this.apiCall('GET', resolvedPath)
  }
}
