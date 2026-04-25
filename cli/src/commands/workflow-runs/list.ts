/**
 * AUTO-GENERATED — DO NOT EDIT
 * Generated from cli-config.yaml by: npm run generate
 */

import { Flags } from '@oclif/core'
import { BaseCommand } from '../../base-command.js'
import { resolvePath } from '../../lib/config-loader.js'

export default class WorkflowRunsList extends BaseCommand {
  static override description = 'List workflow runs'

  static override examples = [
    '<%= config.bin %> workflow-runs list',
    '<%= config.bin %> workflow-runs list --workflow_id value --limit 10',
  ]

  static override flags = {
    ...BaseCommand.baseFlags,
    workflow_id: Flags.string({
      description: 'Filter by workflow ID',
    }),
    status: Flags.string({
      description: 'Filter by run status',
      options: ["running","completed","failed","cancelled"],
    }),
    sort: Flags.string({
      description: 'Sort field',
      options: ["created_at","started_at","completed_at","status"],
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
    const { args, flags } = await this.parse(WorkflowRunsList)
    await this.initApi()

    await this.apiCall('GET', '/workflow-runs',
      { query: {
        workflow_id: flags.workflow_id,
        status: flags.status,
        sort: flags.sort,
        order: flags.order,
        limit: flags.limit,
      } },)
  }
}
