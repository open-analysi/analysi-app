/**
 * AUTO-GENERATED — DO NOT EDIT
 * Generated from cli-config.yaml by: npm run generate
 */

import { Args, Flags } from '@oclif/core'
import { BaseCommand } from '../../base-command.js'
import { resolvePath } from '../../lib/config-loader.js'

export default class WorkflowsGet extends BaseCommand {
  static override description = 'Get workflow details'

  static override examples = [
    '<%= config.bin %> workflows get <workflow_id>',
    '<%= config.bin %> workflows get <workflow_id> --output json',
  ]

  static override args = {
    workflow_id: Args.string({
      description: 'Workflow ID',
      required: true,
    })
  }
  static override flags = {
    ...BaseCommand.baseFlags,
  }

  async run(): Promise<void> {
    const { args, flags } = await this.parse(WorkflowsGet)
    await this.initApi()
    const resolvedPath = resolvePath('/workflows/{workflow_id}', args as Record<string, string>)

    await this.apiCall('GET', resolvedPath)
  }
}
