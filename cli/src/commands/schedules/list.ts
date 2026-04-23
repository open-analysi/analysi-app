/**
 * AUTO-GENERATED — DO NOT EDIT
 * Generated from cli-config.yaml by: npm run generate
 */

import { Flags } from '@oclif/core'
import { BaseCommand } from '../../base-command.js'
import { resolvePath } from '../../lib/config-loader.js'

export default class SchedulesList extends BaseCommand {
  static override description = 'List schedules with optional filters'

  static override examples = [
    '<%= config.bin %> schedules list',
    '<%= config.bin %> schedules list --target_type task --limit 10',
  ]

  static override flags = {
    ...BaseCommand.baseFlags,
    target_type: Flags.string({
      description: 'Filter by target type',
      options: ["task","workflow"],
    }),
    integration_id: Flags.string({
      description: 'Filter by integration ID',
    }),
    origin_type: Flags.string({
      description: 'Filter by origin type',
    }),
    enabled: Flags.boolean({
      description: 'Filter by enabled status',
    }),
    skip: Flags.integer({
      description: 'Offset for pagination',
      default: 0,
    }),
    limit: Flags.integer({
      description: 'Maximum number of results',
      default: 50,
    }),
  }

  async run(): Promise<void> {
    const { args, flags } = await this.parse(SchedulesList)
    await this.initApi()

    await this.apiCall('GET', '/schedules',
      { query: {
        target_type: flags.target_type,
        integration_id: flags.integration_id,
        origin_type: flags.origin_type,
        enabled: flags.enabled,
        skip: flags.skip,
        limit: flags.limit,
      } },)
  }
}
