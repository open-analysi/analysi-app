/**
 * Hand-written workflow run command with live progress tracking.
 *
 * Default: submits workflow execution and shows a live progress view that
 * polls status and graph endpoints, showing node completions as they happen.
 * Use --no-watch for fire-and-forget.
 *
 * Supports --example <n> to use a workflow's built-in data samples as input,
 * and --list-examples to show available samples.
 */

import { Args, Flags } from '@oclif/core'
import chalk from 'chalk'

import { BaseCommand } from '../../base-command.js'
import { resolvePath } from '../../lib/config-loader.js'
import { parseDataFlag } from '../../lib/data-reader.js'
import { listExamples, resolveExample, type DataSample } from '../../lib/data-samples.js'
import type { OutputFormat, PrintOptions } from '../../lib/output.js'
import { printResponse } from '../../lib/output.js'
import { WorkflowProgressWatcher } from '../../lib/workflow-progress.js'

interface RunResponse {
  workflow_run_id: string
  status: string
  message: string
}

interface WorkflowDetail {
  id: string
  name: string
  data_samples: DataSample[] | null
}

export default class WorkflowsRun extends BaseCommand {
  static override description = 'Execute a workflow with live progress tracking'

  static override examples = [
    '<%= config.bin %> workflows run <workflow_id>',
    '<%= config.bin %> workflows run <workflow_id> --data @input.json',
    '<%= config.bin %> workflows run <workflow_id> --example 1',
    '<%= config.bin %> workflows run <workflow_id> --list-examples',
    '<%= config.bin %> workflows run <workflow_id> --no-watch',
  ]

  static override args = {
    workflow_id: Args.string({
      description: 'Workflow ID to execute',
      required: true,
    }),
  }

  static override flags = {
    ...BaseCommand.baseFlags,
    data: Flags.string({
      description: 'JSON input data (or @filepath to read from file)',
    }),
    example: Flags.integer({
      description: 'Use a built-in data sample as input (1-based index)',
      char: 'e',
    }),
    'list-examples': Flags.boolean({
      description: 'List available data samples and exit',
      default: false,
    }),
    watch: Flags.boolean({
      description: 'Watch workflow progress live (default: true)',
      default: true,
      allowNo: true,
    }),
  }

  async run(): Promise<void> {
    const { args, flags } = await this.parse(WorkflowsRun)
    await this.initApi()

    // --list-examples: show available samples and exit
    if (flags['list-examples']) {
      const workflow = await this.fetchWorkflow(args.workflow_id)
      listExamples(workflow, args.workflow_id, {
        entityType: 'workflow',
        runCommand: 'analysi workflows run',
      })
      return
    }

    // Resolve input data from --data or --example
    let inputData: unknown
    if (flags.data && flags.example) {
      this.error('Use either --data or --example, not both')
    } else if (flags.example) {
      const workflow = await this.fetchWorkflow(args.workflow_id)
      inputData = resolveExample(workflow.data_samples, flags.example, 'workflow', (msg) => this.error(msg))
    } else if (flags.data) {
      inputData = parseDataFlag(flags.data as string)
    }

    const resolvedPath = resolvePath('/workflows/{workflow_id}/run', args as Record<string, string>)

    const body: Record<string, unknown> = {}
    if (inputData !== undefined) {
      body.input_data = inputData
    }

    const response = await this.client.request<RunResponse>(
      'POST',
      resolvedPath,
      this.tenantId,
      { body: Object.keys(body).length > 0 ? body : undefined },
    )

    const result = response.data

    // If --no-watch or non-table output, just print and exit
    if (!flags.watch || flags.output !== 'table') {
      const printOpts: PrintOptions = {
        format: flags.output as OutputFormat,
        fields: flags.fields ? (flags.fields as string).split(',').map((f) => f.trim()) : undefined,
        noHeader: flags['no-header'] as boolean,
      }

      printResponse(response, printOpts)
      return
    }

    // Start live progress view
    console.log()
    console.log(chalk.bold(`  Running workflow ${args.workflow_id.slice(0, 8)}...`))
    console.log(chalk.dim(`  run: ${result.workflow_run_id}`))
    if (flags.example) {
      console.log(chalk.dim(`  using example #${flags.example}`))
    }

    console.log()

    const watcher = new WorkflowProgressWatcher(this.client, this.tenantId)
    await watcher.watch(result.workflow_run_id)
  }

  private async fetchWorkflow(workflowId: string): Promise<WorkflowDetail> {
    const path = resolvePath('/workflows/{workflow_id}', { workflow_id: workflowId })
    const response = await this.client.request<WorkflowDetail>('GET', path, this.tenantId)
    return response.data
  }
}
