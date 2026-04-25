/**
 * AUTO-GENERATED — DO NOT EDIT
 * Generated from cli-config.yaml by: npm run generate
 */

import { Args, Flags } from '@oclif/core'
import { BaseCommand } from '../../base-command.js'
import { resolvePath } from '../../lib/config-loader.js'

export default class SchedulesDelete extends BaseCommand {
  static override description = 'Delete a schedule'

  static override examples = [
    '<%= config.bin %> schedules delete <schedule_id>',
  ]

  static override args = {
    schedule_id: Args.string({
      description: 'Schedule ID to delete',
      required: true,
    })
  }
  static override flags = {
    ...BaseCommand.baseFlags,
  }

  async run(): Promise<void> {
    const { args, flags } = await this.parse(SchedulesDelete)
    await this.initApi()
    const resolvedPath = resolvePath('/schedules/{schedule_id}', args as Record<string, string>)

    await this.apiCall('DELETE', resolvedPath)
  }
}
