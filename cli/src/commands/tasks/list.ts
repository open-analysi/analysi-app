/**
 * AUTO-GENERATED — DO NOT EDIT
 * Generated from cli-config.yaml by: npm run generate
 */

import { Flags } from '@oclif/core'
import { BaseCommand } from '../../base-command.js'
import { resolvePath } from '../../lib/config-loader.js'

export default class TasksList extends BaseCommand {
  static override description = 'List tasks'

  static override examples = [
    '<%= config.bin %> tasks list',
    '<%= config.bin %> tasks list --function value --limit 10',
  ]

  static override flags = {
    ...BaseCommand.baseFlags,
    function: Flags.string({
      description: 'Filter by task function',
    }),
    scope: Flags.string({
      description: 'Filter by task scope',
    }),
    q: Flags.string({
      description: 'Search query (name, description, tags)',
    }),
    limit: Flags.integer({
      description: 'Maximum number of results',
      default: 25,
    }),
  }

  async run(): Promise<void> {
    const { args, flags } = await this.parse(TasksList)
    await this.initApi()

    await this.apiCall('GET', '/tasks',
      { query: {
        function: flags.function,
        scope: flags.scope,
        q: flags.q,
        limit: flags.limit,
      } },)
  }
}
