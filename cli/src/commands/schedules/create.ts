/**
 * AUTO-GENERATED — DO NOT EDIT
 * Generated from cli-config.yaml by: npm run generate
 */

import { Flags } from '@oclif/core'
import { BaseCommand } from '../../base-command.js'
import { resolvePath } from '../../lib/config-loader.js'
import { parseDataFlag } from '../../lib/data-reader.js'

export default class SchedulesCreate extends BaseCommand {
  static override description = 'Create a new schedule'

  static override examples = [
    '<%= config.bin %> schedules create',
  ]

  static override flags = {
    ...BaseCommand.baseFlags,
    data: Flags.string({
      description: 'JSON schedule data (or @filepath). Fields: target_type, target_id, schedule_type, schedule_value, timezone, enabled, params',
      required: true,
    }),
  }

  async run(): Promise<void> {
    const { args, flags } = await this.parse(SchedulesCreate)
    await this.initApi()

    await this.apiCall('POST', '/schedules',
      { body: flags.data ? parseDataFlag(flags.data as string) : undefined },)
  }
}
