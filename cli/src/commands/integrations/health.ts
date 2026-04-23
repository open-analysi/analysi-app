/**
 * AUTO-GENERATED — DO NOT EDIT
 * Generated from cli-config.yaml by: npm run generate
 */

import { Args, Flags } from '@oclif/core'
import { BaseCommand } from '../../base-command.js'
import { resolvePath } from '../../lib/config-loader.js'

export default class IntegrationsHealth extends BaseCommand {
  static override description = 'Check integration health'

  static override examples = [
    '<%= config.bin %> integrations health <integration_id>',
    '<%= config.bin %> integrations health <integration_id> --output json',
  ]

  static override args = {
    integration_id: Args.string({
      description: 'Integration ID',
      required: true,
    })
  }
  static override flags = {
    ...BaseCommand.baseFlags,
  }

  async run(): Promise<void> {
    const { args, flags } = await this.parse(IntegrationsHealth)
    await this.initApi()
    const resolvedPath = resolvePath('/integrations/{integration_id}/health', args as Record<string, string>)

    await this.apiCall('GET', resolvedPath)
  }
}
