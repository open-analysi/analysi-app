/**
 * AUTO-GENERATED — DO NOT EDIT
 * Generated from cli-config.yaml by: npm run generate
 */

import { Args, Flags } from '@oclif/core'
import { BaseCommand } from '../../base-command.js'
import { resolvePath } from '../../lib/config-loader.js'

export default class TaskRunsGet extends BaseCommand {
  static override description = 'Get task run details'

  static override examples = [
    '<%= config.bin %> task-runs get <task_run_id>',
    '<%= config.bin %> task-runs get <task_run_id> --output json',
  ]

  static override args = {
    task_run_id: Args.string({
      description: 'Task run ID',
      required: true,
    })
  }
  static override flags = {
    ...BaseCommand.baseFlags,
  }

  async run(): Promise<void> {
    const { args, flags } = await this.parse(TaskRunsGet)
    await this.initApi()
    const resolvedPath = resolvePath('/task-runs/{task_run_id}', args as Record<string, string>)

    await this.apiCall('GET', resolvedPath)
  }
}
