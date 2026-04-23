/**
 * AUTO-GENERATED — DO NOT EDIT
 * Generated from cli-config.yaml by: npm run generate
 */

import { Flags } from '@oclif/core'
import { BaseCommand } from '../../base-command.js'
import { resolvePath } from '../../lib/config-loader.js'

export default class IntegrationsList extends BaseCommand {
  static override description = 'List configured integrations'

  static override examples = [
    '<%= config.bin %> integrations list',
    '<%= config.bin %> integrations list --enabled --limit 10',
  ]

  static override flags = {
    ...BaseCommand.baseFlags,
    enabled: Flags.boolean({
      description: 'Filter by enabled status',
    }),
  }

  async run(): Promise<void> {
    const { args, flags } = await this.parse(IntegrationsList)
    await this.initApi()

    await this.apiCall('GET', '/integrations',
      { query: {
        enabled: flags.enabled,
      } },)
  }
}
