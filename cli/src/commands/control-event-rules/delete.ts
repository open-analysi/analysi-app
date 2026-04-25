/**
 * AUTO-GENERATED — DO NOT EDIT
 * Generated from cli-config.yaml by: npm run generate
 */

import { Args, Flags } from '@oclif/core'
import { BaseCommand } from '../../base-command.js'
import { resolvePath } from '../../lib/config-loader.js'

export default class ControlEventRulesDelete extends BaseCommand {
  static override description = 'Delete a control event rule'

  static override examples = [
    '<%= config.bin %> control-event-rules delete <rule_id>',
  ]

  static override args = {
    rule_id: Args.string({
      description: 'Rule ID to delete',
      required: true,
    })
  }
  static override flags = {
    ...BaseCommand.baseFlags,
  }

  async run(): Promise<void> {
    const { args, flags } = await this.parse(ControlEventRulesDelete)
    await this.initApi()
    const resolvedPath = resolvePath('/control-event-rules/{rule_id}', args as Record<string, string>)

    await this.apiCall('DELETE', resolvedPath)
  }
}
