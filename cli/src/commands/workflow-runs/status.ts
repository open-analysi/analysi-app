/**
 * AUTO-GENERATED — DO NOT EDIT
 * Generated from cli-config.yaml by: npm run generate
 */

import { Args, Flags } from '@oclif/core'
import { BaseCommand } from '../../base-command.js'
import { resolvePath } from '../../lib/config-loader.js'

export default class WorkflowRunsStatus extends BaseCommand {
  static override description = 'Get workflow run status'

  static override examples = [
    '<%= config.bin %> workflow-runs status <workflow_run_id>',
    '<%= config.bin %> workflow-runs status <workflow_run_id> --output json',
  ]

  static override args = {
    workflow_run_id: Args.string({
      description: 'Workflow run ID',
      required: true,
    })
  }
  static override flags = {
    ...BaseCommand.baseFlags,
  }

  async run(): Promise<void> {
    const { args, flags } = await this.parse(WorkflowRunsStatus)
    await this.initApi()
    const resolvedPath = resolvePath('/workflow-runs/{workflow_run_id}/status', args as Record<string, string>)

    await this.apiCall('GET', resolvedPath)
  }
}
