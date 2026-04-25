/**
 * AUTO-GENERATED — DO NOT EDIT
 * Generated from cli-config.yaml by: npm run generate
 */

import { Flags } from '@oclif/core'
import { BaseCommand } from '../../base-command.js'
import { resolvePath } from '../../lib/config-loader.js'

export default class ControlEventRulesList extends BaseCommand {
  static override description = 'List control event rules'

  static override examples = [
    '<%= config.bin %> control-event-rules list',
    '<%= config.bin %> control-event-rules list --channel value --limit 10',
  ]

  static override flags = {
    ...BaseCommand.baseFlags,
    channel: Flags.string({
      description: 'Filter by channel',
    }),
    enabled_only: Flags.boolean({
      description: 'Return only enabled rules',
    }),
  }

  async run(): Promise<void> {
    const { args, flags } = await this.parse(ControlEventRulesList)
    await this.initApi()

    await this.apiCall('GET', '/control-event-rules',
      { query: {
        channel: flags.channel,
        enabled_only: flags.enabled_only,
      } },)
  }
}
