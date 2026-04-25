/**
 * AUTO-GENERATED — DO NOT EDIT
 * Generated from cli-config.yaml by: npm run generate
 */

import { Flags } from '@oclif/core'
import { BaseCommand } from '../../base-command.js'
import { resolvePath } from '../../lib/config-loader.js'

export default class WorkflowsList extends BaseCommand {
  static override description = 'List workflows'

  static override examples = [
    '<%= config.bin %> workflows list',
    '<%= config.bin %> workflows list --name value --limit 10',
  ]

  static override flags = {
    ...BaseCommand.baseFlags,
    name: Flags.string({
      description: 'Filter by workflow name',
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
    const { args, flags } = await this.parse(WorkflowsList)
    await this.initApi()

    await this.apiCall('GET', '/workflows',
      { query: {
        name: flags.name,
        limit: flags.limit,
        offset: flags.offset,
      } },)
  }
}
