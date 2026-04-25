/**
 * AUTO-GENERATED — DO NOT EDIT
 * Generated from cli-config.yaml by: npm run generate
 */

import { Args, Flags } from '@oclif/core'
import { BaseCommand } from '../../base-command.js'
import { resolvePath } from '../../lib/config-loader.js'
import { parseDataFlag } from '../../lib/data-reader.js'

export default class ControlEventRulesUpdate extends BaseCommand {
  static override description = 'Update a control event rule'

  static override examples = [
    '<%= config.bin %> control-event-rules update <rule_id>',
  ]

  static override args = {
    rule_id: Args.string({
      description: 'Rule ID',
      required: true,
    })
  }
  static override flags = {
    ...BaseCommand.baseFlags,
    data: Flags.string({
      description: 'JSON update data (or @filepath). Fields: channel, target_type, target_id, name, enabled, config',
      required: true,
    }),
  }

  async run(): Promise<void> {
    const { args, flags } = await this.parse(ControlEventRulesUpdate)
    await this.initApi()
    const resolvedPath = resolvePath('/control-event-rules/{rule_id}', args as Record<string, string>)

    await this.apiCall('PATCH', resolvedPath,
      { body: flags.data ? parseDataFlag(flags.data as string) : undefined },)
  }
}
