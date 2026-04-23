/**
 * Hand-written task run command with live progress tracking.
 *
 * Default: submits task execution and polls until completion, showing the
 * result. Use --no-watch for fire-and-forget.
 *
 * Supports --example <n> to use a task's built-in data samples as input,
 * and --list-examples to show available samples.
 */

import { Args, Flags } from '@oclif/core'
import chalk from 'chalk'

import { BaseCommand } from '../../base-command.js'
import { elapsed, formatDuration, sleep } from '../../lib/cli-utils.js'
import { resolvePath } from '../../lib/config-loader.js'
import { parseDataFlag } from '../../lib/data-reader.js'
import { listExamples, resolveExample, type DataSample } from '../../lib/data-samples.js'
import type { OutputFormat, PrintOptions } from '../../lib/output.js'
import { printResponse } from '../../lib/output.js'

interface RunResponse {
  trid: string
  status: string
  message: string
}

interface TaskRunDetail {
  id: string
  task_name: string
  status: string
  duration: string | null
  started_at: string | null
  completed_at: string | null
  error_message?: string | null
}

interface TaskDetail {
  id: string
  name: string
  data_samples: DataSample[] | null
}

export default class TasksRun extends BaseCommand {
  static override description = 'Execute a task with live progress tracking'

  static override examples = [
    '<%= config.bin %> tasks run <task_id>',
    '<%= config.bin %> tasks run <task_id> --data @input.json',
    '<%= config.bin %> tasks run <task_id> --example 1',
    '<%= config.bin %> tasks run <task_id> --list-examples',
    '<%= config.bin %> tasks run <task_id> --no-watch',
  ]

  static override args = {
    task_id: Args.string({
      description: 'Task ID to execute',
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
      description: 'Watch task progress live (default: true)',
      default: true,
      allowNo: true,
    }),
  }

  async run(): Promise<void> {
    const { args, flags } = await this.parse(TasksRun)
    await this.initApi()

    // --list-examples: show available samples and exit
    if (flags['list-examples']) {
      const task = await this.fetchTask(args.task_id)
      listExamples(task, args.task_id, {
        entityType: 'task',
        runCommand: 'analysi tasks run',
      })
      return
    }

    // Resolve input data from --data or --example
    let inputData: unknown
    if (flags.data && flags.example) {
      this.error('Use either --data or --example, not both')
    } else if (flags.example) {
      const task = await this.fetchTask(args.task_id)
      inputData = resolveExample(task.data_samples, flags.example, 'task', (msg) => this.error(msg))
    } else if (flags.data) {
      inputData = parseDataFlag(flags.data as string)
    }

    const resolvedPath = resolvePath('/tasks/{task_id}/run', args as Record<string, string>)

    const body: Record<string, unknown> = {}
    if (inputData !== undefined) {
      body.input = inputData
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
    console.log(chalk.bold(`  Running task ${args.task_id.slice(0, 8)}...`))
    console.log(chalk.dim(`  run: ${result.trid}`))
    if (flags.example) {
      console.log(chalk.dim(`  using example #${flags.example}`))
    }

    console.log()

    await this.watchTaskRun(result.trid)
  }

  private async watchTaskRun(trid: string): Promise<void> {
    const startTime = Date.now()
    const POLL_MS = 2000
    const TIMEOUT_MS = 10 * 60 * 1000 // 10 minutes

    console.log(`  ${chalk.cyan('▸')} Executing ${chalk.dim('(0s)')}`)

    while (Date.now() - startTime < TIMEOUT_MS) {
      const taskRun = await this.fetchSafe<TaskRunDetail>(
        `/task-runs/${encodeURIComponent(trid)}`,
      )

      if (!taskRun) {
        await sleep(POLL_MS)
        continue
      }

      if (taskRun.status === 'completed') {
        const dur = formatDuration(taskRun.duration)
        const el = elapsed(startTime)
        console.log()
        console.log(`  ${chalk.green('✓')} ${taskRun.task_name} complete ${chalk.dim(`(${dur || el})`)}`)
        console.log()
        return
      }

      if (taskRun.status === 'failed') {
        const el = elapsed(startTime)
        console.log()
        console.log(`  ${chalk.red('✗')} ${taskRun.task_name} failed ${chalk.dim(`(${el})`)}`)
        if (taskRun.error_message) {
          const firstLine = taskRun.error_message.split('\n')[0]
          console.log(`    ${chalk.dim(firstLine.slice(0, 120))}`)
        }

        console.log(chalk.dim(`\n  Details: analysi task-runs get ${trid.slice(0, 8)}... --output json`))
        console.log()
        return
      }

      await sleep(POLL_MS)
    }

    // Timeout
    console.log()
    console.log(chalk.yellow(`  ⚠ Timed out after ${elapsed(startTime)}. Task may still be running.`))
    console.log(chalk.dim(`  Check with: analysi task-runs get ${trid}`))
    console.log()
  }

  private async fetchTask(taskId: string): Promise<TaskDetail> {
    const path = resolvePath('/tasks/{task_id}', { task_id: taskId })
    const response = await this.client.request<TaskDetail>('GET', path, this.tenantId)
    return response.data
  }

  private async fetchSafe<T>(path: string): Promise<T | null> {
    try {
      const response = await this.client.request<T>('GET', path, this.tenantId)
      return response.data
    } catch {
      return null
    }
  }
}
