/**
 * Hand-written task update command.
 *
 * Updates a task's script, directive, description, or data samples.
 * Supports @filepath for script and data-samples.
 */

import { Args, Flags } from '@oclif/core'

import { BaseCommand } from '../../base-command.js'
import { resolvePath } from '../../lib/config-loader.js'
import { parseDataFlag } from '../../lib/data-reader.js'
import { readScriptFlag } from '../../lib/script-reader.js'
import type { OutputFormat, PrintOptions } from '../../lib/output.js'
import { printResponse } from '../../lib/output.js'

export default class TasksUpdate extends BaseCommand {
  static override description = 'Update a task (script, directive, description, data samples)'

  static override examples = [
    '<%= config.bin %> tasks update <task_id> --script @updated.cy',
    '<%= config.bin %> tasks update <task_id> --description "Updated enrichment task"',
    '<%= config.bin %> tasks update <task_id> --script @new.cy --directive "Be concise"',
  ]

  static override args = {
    task_id: Args.string({
      description: 'Task ID to update',
      required: true,
    }),
  }

  static override flags = {
    ...BaseCommand.baseFlags,
    script: Flags.string({
      description: 'New Cy script content (or @filepath to read from .cy file)',
    }),
    description: Flags.string({
      description: 'New task description',
    }),
    directive: Flags.string({
      description: 'New system directive for LLM calls',
    }),
    'data-samples': Flags.string({
      description: 'New data samples JSON (or @filepath)',
    }),
    name: Flags.string({
      description: 'New task name',
    }),
  }

  async run(): Promise<void> {
    const { args, flags } = await this.parse(TasksUpdate)
    await this.initApi()

    const body: Record<string, unknown> = {}

    if (flags.script) body.script = readScriptFlag(flags.script as string)
    if (flags.description) body.description = flags.description
    if (flags.directive) body.directive = flags.directive
    if (flags.name) body.name = flags.name
    if (flags['data-samples']) body.data_samples = parseDataFlag(flags['data-samples'] as string)

    if (Object.keys(body).length === 0) {
      this.error('Nothing to update. Provide at least one of: --script, --description, --directive, --name, --data-samples')
    }

    const resolvedPath = resolvePath('/tasks/{task_id}', args as Record<string, string>)
    const response = await this.client.request('PUT', resolvedPath, this.tenantId, { body })

    const printOpts: PrintOptions = {
      format: flags.output as OutputFormat,
      fields: flags.fields ? (flags.fields as string).split(',').map((f) => f.trim()) : undefined,
      noHeader: flags['no-header'] as boolean,
    }

    printResponse(response, printOpts)
  }
}
