/**
 * AUTO-GENERATED — DO NOT EDIT
 * Generated from cli-config.yaml by: npm run generate
 */

import { Args, Flags } from '@oclif/core'
import { BaseCommand } from '../../base-command.js'
import { resolvePath } from '../../lib/config-loader.js'

export default class KnowledgeUnitsGetTable extends BaseCommand {
  static override description = 'Get a table knowledge unit'

  static override examples = [
    '<%= config.bin %> knowledge-units get-table <id>',
  ]

  static override args = {
    id: Args.string({
      description: 'Table KU ID',
      required: true,
    })
  }
  static override flags = {
    ...BaseCommand.baseFlags,
  }

  async run(): Promise<void> {
    const { args, flags } = await this.parse(KnowledgeUnitsGetTable)
    await this.initApi()
    const resolvedPath = resolvePath('/knowledge-units/tables/{id}', args as Record<string, string>)

    await this.apiCall('GET', resolvedPath)
  }
}
