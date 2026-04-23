/**
 * AUTO-GENERATED — DO NOT EDIT
 * Generated from cli-config.yaml by: npm run generate
 */

import { Flags } from '@oclif/core'
import { BaseCommand } from '../../base-command.js'
import { resolvePath } from '../../lib/config-loader.js'
import { parseDataFlag } from '../../lib/data-reader.js'

export default class ControlEventRulesCreate extends BaseCommand {
  static override description = 'Create a control event rule'

  static override examples = [
    '<%= config.bin %> control-event-rules create',
  ]

  static override flags = {
    ...BaseCommand.baseFlags,
    data: Flags.string({
      description: 'JSON rule data (or @filepath). Fields: channel, target_type, target_id, name, enabled, config',
      required: true,
    }),
  }

  async run(): Promise<void> {
    const { args, flags } = await this.parse(ControlEventRulesCreate)
    await this.initApi()

    await this.apiCall('POST', '/control-event-rules',
      { body: flags.data ? parseDataFlag(flags.data as string) : undefined },)
  }
}
