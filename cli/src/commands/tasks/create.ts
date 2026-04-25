/**
 * Hand-written task create command.
 *
 * Creates a new task with a Cy script. Supports reading the script from
 * a file via @filepath syntax.
 */

import { Flags } from '@oclif/core'

import { BaseCommand } from '../../base-command.js'
import { parseDataFlag } from '../../lib/data-reader.js'
import { readScriptFlag } from '../../lib/script-reader.js'
import type { OutputFormat, PrintOptions } from '../../lib/output.js'
import { printResponse } from '../../lib/output.js'

export default class TasksCreate extends BaseCommand {
  static override description = 'Create a new task with a Cy script'

  static override examples = [
    '<%= config.bin %> tasks create --name "IP Enrichment" --script @enrich_ip.cy',
    '<%= config.bin %> tasks create --name "Triage" --script @triage.cy --function reasoning --scope processing',
    '<%= config.bin %> tasks create --name "Quick" --script \'result = "hello"\'',
  ]

  static override flags = {
    ...BaseCommand.baseFlags,
    name: Flags.string({
      description: 'Task name',
      required: true,
    }),
    script: Flags.string({
      description: 'Cy script content (or @filepath to read from .cy file)',
      required: true,
    }),
    description: Flags.string({
      description: 'Task description',
    }),
    'cy-name': Flags.string({
      description: 'Script-friendly identifier (auto-generated if omitted)',
    }),
    function: Flags.string({
      description: 'Task function type (e.g. search, enrichment, reasoning, summarization, notification, action, data_conversion)',
    }),
    scope: Flags.string({
      description: 'Task scope',
      options: ['input', 'processing', 'output'],
    }),
    directive: Flags.string({
      description: 'System directive for LLM calls',
    }),
    tags: Flags.string({
      description: 'Comma-separated tags/categories',
    }),
    'data-samples': Flags.string({
      description: 'JSON data samples (or @filepath)',
    }),
  }

  async run(): Promise<void> {
    const { flags } = await this.parse(TasksCreate)
    await this.initApi()

    const script = readScriptFlag(flags.script as string)

    const body: Record<string, unknown> = {
      name: flags.name,
      script,
    }

    if (flags.description) body.description = flags.description
    if (flags['cy-name']) body.cy_name = flags['cy-name']
    if (flags.function) body.function = flags.function
    if (flags.scope) body.scope = flags.scope
    if (flags.directive) body.directive = flags.directive
    if (flags.tags) body.categories = (flags.tags as string).split(',').map((t) => t.trim())
    if (flags['data-samples']) body.data_samples = parseDataFlag(flags['data-samples'] as string)

    const response = await this.client.request('POST', '/tasks', this.tenantId, { body })

    const printOpts: PrintOptions = {
      format: flags.output as OutputFormat,
      fields: flags.fields ? (flags.fields as string).split(',').map((f) => f.trim()) : undefined,
      noHeader: flags['no-header'] as boolean,
    }

    printResponse(response, printOpts)
  }
}
