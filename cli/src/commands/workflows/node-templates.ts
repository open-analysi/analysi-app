/**
 * AUTO-GENERATED — DO NOT EDIT
 * Generated from cli-config.yaml by: npm run generate
 */

import { Flags } from '@oclif/core'
import { BaseCommand } from '../../base-command.js'
import { resolvePath } from '../../lib/config-loader.js'

export default class WorkflowsNodeTemplates extends BaseCommand {
  static override description = 'List available workflow node templates (identity, merge, collect)'

  static override examples = [
    '<%= config.bin %> workflows node-templates',
  ]

  static override flags = {
    ...BaseCommand.baseFlags,
    name: Flags.string({
      description: 'Filter by template name',
    }),
    enabled_only: Flags.boolean({
      description: 'Only return enabled templates',
    }),
  }

  async run(): Promise<void> {
    const { args, flags } = await this.parse(WorkflowsNodeTemplates)
    await this.initApi()

    await this.apiCall('GET', '/workflows/node-templates',
      { query: {
        name: flags.name,
        enabled_only: flags.enabled_only,
      } },)
  }
}
