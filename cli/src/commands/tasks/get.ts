/**
 * AUTO-GENERATED — DO NOT EDIT
 * Generated from cli-config.yaml by: npm run generate
 */

import { Args, Flags } from '@oclif/core'
import { BaseCommand } from '../../base-command.js'
import { resolvePath } from '../../lib/config-loader.js'

export default class TasksGet extends BaseCommand {
  static override description = 'Get task details'

  static override examples = [
    '<%= config.bin %> tasks get <task_id>',
    '<%= config.bin %> tasks get <task_id> --output json',
  ]

  static override args = {
    task_id: Args.string({
      description: 'Task ID',
      required: true,
    })
  }
  static override flags = {
    ...BaseCommand.baseFlags,
  }

  async run(): Promise<void> {
    const { args, flags } = await this.parse(TasksGet)
    await this.initApi()
    const resolvedPath = resolvePath('/tasks/{task_id}', args as Record<string, string>)

    await this.apiCall('GET', resolvedPath)
  }
}
