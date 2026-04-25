/**
 * AUTO-GENERATED — DO NOT EDIT
 * Generated from cli-config.yaml by: npm run generate
 */

import { Flags } from '@oclif/core'
import { BaseCommand } from '../../base-command.js'
import { resolvePath } from '../../lib/config-loader.js'

export default class KnowledgeUnitsSearch extends BaseCommand {
  static override description = 'Search across all knowledge unit types'

  static override examples = [
    '<%= config.bin %> knowledge-units search',
  ]

  static override flags = {
    ...BaseCommand.baseFlags,
    q: Flags.string({
      description: 'Search query (name, description)',
    }),
    ku_type: Flags.string({
      description: 'Filter by KU type',
      options: ["table","document","index"],
    }),
    status: Flags.string({
      description: 'Filter by status',
      options: ["enabled","disabled"],
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
    const { args, flags } = await this.parse(KnowledgeUnitsSearch)
    await this.initApi()

    await this.apiCall('GET', '/knowledge-units',
      { query: {
        q: flags.q,
        ku_type: flags.ku_type,
        status: flags.status,
        limit: flags.limit,
        offset: flags.offset,
      } },)
  }
}
