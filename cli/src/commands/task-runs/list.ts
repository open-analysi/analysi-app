/**
 * AUTO-GENERATED — DO NOT EDIT
 * Generated from cli-config.yaml by: npm run generate
 */

import { Flags } from '@oclif/core'
import { BaseCommand } from '../../base-command.js'
import { resolvePath } from '../../lib/config-loader.js'

export default class TaskRunsList extends BaseCommand {
  static override description = 'List task runs'

  static override examples = [
    '<%= config.bin %> task-runs list',
    '<%= config.bin %> task-runs list --task_id value --limit 10',
  ]

  static override flags = {
    ...BaseCommand.baseFlags,
    task_id: Flags.string({
      description: 'Filter by task ID',
    }),
    workflow_run_id: Flags.string({
      description: 'Filter by workflow run ID',
    }),
    status: Flags.string({
      description: 'Filter by run status',
      options: ["running","completed","failed"],
    }),
    sort: Flags.string({
      description: 'Sort field',
      options: ["created_at","updated_at","status","duration"],
    }),
    order: Flags.string({
      description: 'Sort order (asc, desc)',
      options: ["asc","desc"],
    }),
    limit: Flags.integer({
      description: 'Maximum number of results',
      default: 25,
    }),
  }

  async run(): Promise<void> {
    const { args, flags } = await this.parse(TaskRunsList)
    await this.initApi()

    await this.apiCall('GET', '/task-runs',
      { query: {
        task_id: flags.task_id,
        workflow_run_id: flags.workflow_run_id,
        status: flags.status,
        sort: flags.sort,
        order: flags.order,
        limit: flags.limit,
      } },)
  }
}
