/**
 * AUTO-GENERATED — DO NOT EDIT
 * Generated from cli-config.yaml by: npm run generate
 */

import { Args, Flags } from '@oclif/core'
import { BaseCommand } from '../../base-command.js'
import { resolvePath } from '../../lib/config-loader.js'

export default class IntegrationsGet extends BaseCommand {
  static override description = 'Get integration details'

  static override examples = [
    '<%= config.bin %> integrations get <integration_id>',
    '<%= config.bin %> integrations get <integration_id> --output json',
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
    const { args, flags } = await this.parse(IntegrationsGet)
    await this.initApi()
    const resolvedPath = resolvePath('/integrations/{integration_id}', args as Record<string, string>)

    await this.apiCall('GET', resolvedPath)
  }
}
