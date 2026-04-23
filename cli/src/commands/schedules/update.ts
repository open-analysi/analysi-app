/**
 * AUTO-GENERATED — DO NOT EDIT
 * Generated from cli-config.yaml by: npm run generate
 */

import { Args, Flags } from '@oclif/core'
import { BaseCommand } from '../../base-command.js'
import { resolvePath } from '../../lib/config-loader.js'
import { parseDataFlag } from '../../lib/data-reader.js'

export default class SchedulesUpdate extends BaseCommand {
  static override description = 'Update a schedule'

  static override examples = [
    '<%= config.bin %> schedules update <schedule_id>',
  ]

  static override args = {
    schedule_id: Args.string({
      description: 'Schedule ID',
      required: true,
    })
  }
  static override flags = {
    ...BaseCommand.baseFlags,
    data: Flags.string({
      description: 'JSON update data (or @filepath). Fields: schedule_value, timezone, enabled, params',
      required: true,
    }),
  }

  async run(): Promise<void> {
    const { args, flags } = await this.parse(SchedulesUpdate)
    await this.initApi()
    const resolvedPath = resolvePath('/schedules/{schedule_id}', args as Record<string, string>)

    await this.apiCall('PATCH', resolvedPath,
      { body: flags.data ? parseDataFlag(flags.data as string) : undefined },)
  }
}
