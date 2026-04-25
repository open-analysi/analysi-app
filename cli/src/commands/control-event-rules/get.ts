/**
 * AUTO-GENERATED — DO NOT EDIT
 * Generated from cli-config.yaml by: npm run generate
 */

import { Args, Flags } from '@oclif/core'
import { BaseCommand } from '../../base-command.js'
import { resolvePath } from '../../lib/config-loader.js'

export default class ControlEventRulesGet extends BaseCommand {
  static override description = 'Get a control event rule'

  static override examples = [
    '<%= config.bin %> control-event-rules get <rule_id>',
    '<%= config.bin %> control-event-rules get <rule_id> --output json',
  ]

  static override args = {
    rule_id: Args.string({
      description: 'Rule ID',
      required: true,
    })
  }
  static override flags = {
    ...BaseCommand.baseFlags,
  }

  async run(): Promise<void> {
    const { args, flags } = await this.parse(ControlEventRulesGet)
    await this.initApi()
    const resolvedPath = resolvePath('/control-event-rules/{rule_id}', args as Record<string, string>)

    await this.apiCall('GET', resolvedPath)
  }
}
