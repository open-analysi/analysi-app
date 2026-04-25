/**
 * AUTO-GENERATED — DO NOT EDIT
 * Generated from cli-config.yaml by: npm run generate
 */

import { Flags } from '@oclif/core'
import { BaseCommand } from '../../base-command.js'
import { resolvePath } from '../../lib/config-loader.js'

export default class SkillsList extends BaseCommand {
  static override description = 'List skills with optional search and filters'

  static override examples = [
    '<%= config.bin %> skills list',
    '<%= config.bin %> skills list --q value --limit 10',
  ]

  static override flags = {
    ...BaseCommand.baseFlags,
    q: Flags.string({
      description: 'Search query (name, description, categories)',
    }),
    status: Flags.string({
      description: 'Filter by status',
      options: ["enabled","disabled"],
    }),
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
    const { args, flags } = await this.parse(SkillsList)
    await this.initApi()

    await this.apiCall('GET', '/skills',
      { query: {
        q: flags.q,
        status: flags.status,
        app: flags.app,
        limit: flags.limit,
        offset: flags.offset,
      } },)
  }
}
