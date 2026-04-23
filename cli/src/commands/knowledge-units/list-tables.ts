/**
 * AUTO-GENERATED — DO NOT EDIT
 * Generated from cli-config.yaml by: npm run generate
 */

import { Flags } from '@oclif/core'
import { BaseCommand } from '../../base-command.js'
import { resolvePath } from '../../lib/config-loader.js'

export default class KnowledgeUnitsListTables extends BaseCommand {
  static override description = 'List table knowledge units'

  static override examples = [
    '<%= config.bin %> knowledge-units list-tables',
  ]

  static override flags = {
    ...BaseCommand.baseFlags,
    app: Flags.string({
      description: 'Filter by content pack name',
    }),
    limit: Flags.integer({
      description: 'Maximum number of results',
      default: 25,
    }),
    offset: Flags.integer({
      description: 'Offset for pagination',
      default: 0,
    }),
  }

  async run(): Promise<void> {
    const { args, flags } = await this.parse(KnowledgeUnitsListTables)
    await this.initApi()

    await this.apiCall('GET', '/knowledge-units/tables',
      { query: {
        app: flags.app,
        limit: flags.limit,
        offset: flags.offset,
      } },)
  }
}
