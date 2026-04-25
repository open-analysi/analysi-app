/**
 * AUTO-GENERATED — DO NOT EDIT
 * Generated from cli-config.yaml by: npm run generate
 */

import { Flags } from '@oclif/core'
import { BaseCommand } from '../../base-command.js'
import { resolvePath } from '../../lib/config-loader.js'

export default class AlertsSearch extends BaseCommand {
  static override description = 'Search alerts by query'

  static override examples = [
    '<%= config.bin %> alerts search',
  ]

  static override flags = {
    ...BaseCommand.baseFlags,
    q: Flags.string({
      description: 'Search query',
      required: true,
    }),
    limit: Flags.integer({
      description: 'Maximum number of results',
      default: 25,
    }),
  }

  async run(): Promise<void> {
    const { args, flags } = await this.parse(AlertsSearch)
    await this.initApi()

    await this.apiCall('GET', '/alerts/search',
      { query: {
        q: flags.q,
        limit: flags.limit,
      } },)
  }
}
