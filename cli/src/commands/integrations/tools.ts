/**
 * AUTO-GENERATED — DO NOT EDIT
 * Generated from cli-config.yaml by: npm run generate
 */

import { Args, Flags } from '@oclif/core'
import { BaseCommand } from '../../base-command.js'
import { resolvePath } from '../../lib/config-loader.js'

export default class IntegrationsTools extends BaseCommand {
  static override description = 'List tools available for an integration type'

  static override examples = [
    '<%= config.bin %> integrations tools <integration_type>',
  ]

  static override args = {
    integration_type: Args.string({
      description: 'Integration TYPE (e.g. splunk, virustotal), not instance ID',
      required: true,
    })
  }
  static override flags = {
    ...BaseCommand.baseFlags,
  }

  async run(): Promise<void> {
    const { args, flags } = await this.parse(IntegrationsTools)
    await this.initApi()
    const resolvedPath = resolvePath('/integrations/registry/{integration_type}', args as Record<string, string>)

    await this.apiCall('GET', resolvedPath)
  }
}
