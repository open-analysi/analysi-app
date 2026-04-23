/**
 * AUTO-GENERATED — DO NOT EDIT
 * Generated from cli-config.yaml by: npm run generate
 */

import { Args, Flags } from '@oclif/core'
import { BaseCommand } from '../../base-command.js'
import { resolvePath } from '../../lib/config-loader.js'

export default class AlertsGet extends BaseCommand {
  static override description = 'Get alert details'

  static override examples = [
    '<%= config.bin %> alerts get <alert_id>',
    '<%= config.bin %> alerts get <alert_id> --output json',
  ]

  static override args = {
    alert_id: Args.string({
      description: 'Alert ID',
      required: true,
    })
  }
  static override flags = {
    ...BaseCommand.baseFlags,
  }

  async run(): Promise<void> {
    const { args, flags } = await this.parse(AlertsGet)
    await this.initApi()
    const resolvedPath = resolvePath('/alerts/{alert_id}', args as Record<string, string>)

    await this.apiCall('GET', resolvedPath)
  }
}
