/**
 * AUTO-GENERATED — DO NOT EDIT
 * Generated from cli-config.yaml by: npm run generate
 */

import { Args, Flags } from '@oclif/core'
import { BaseCommand } from '../../base-command.js'
import { resolvePath } from '../../lib/config-loader.js'
import { parseDataFlag } from '../../lib/data-reader.js'

export default class WorkflowsUpdate extends BaseCommand {
  static override description = 'Update workflow metadata'

  static override examples = [
    '<%= config.bin %> workflows update <workflow_id>',
  ]

  static override args = {
    workflow_id: Args.string({
      description: 'Workflow ID',
      required: true,
    })
  }
  static override flags = {
    ...BaseCommand.baseFlags,
    data: Flags.string({
      description: 'JSON update data (or @filepath). Fields: name, description, io_schema, data_samples',
      required: true,
    }),
  }

  async run(): Promise<void> {
    const { args, flags } = await this.parse(WorkflowsUpdate)
    await this.initApi()
    const resolvedPath = resolvePath('/workflows/{workflow_id}', args as Record<string, string>)

    await this.apiCall('PATCH', resolvedPath,
      { body: flags.data ? parseDataFlag(flags.data as string) : undefined },)
  }
}
