/**
 * Hand-written ad-hoc task execution command.
 *
 * Executes a Cy script without creating a saved task.
 * Submits via POST /tasks/run and polls for completion with progress.
 */

import { Args, Flags } from '@oclif/core'
import chalk from 'chalk'

import { BaseCommand } from '../../base-command.js'
import { elapsed, formatDuration, sleep } from '../../lib/cli-utils.js'
import { parseDataFlag } from '../../lib/data-reader.js'
import { readScriptFlag } from '../../lib/script-reader.js'
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

export default class TasksRunAdhoc extends BaseCommand {
  static override description = 'Execute a Cy script ad-hoc without a saved task'

  static override examples = [
    '<%= config.bin %> tasks run-adhoc @script.cy',
    '<%= config.bin %> tasks run-adhoc @enrich.cy --data @input.json',
    '<%= config.bin %> tasks run-adhoc \'result = sum([1, 2, 3])\'',
    '<%= config.bin %> tasks run-adhoc @script.cy --no-watch',
  ]

  static override args = {
    script: Args.string({
      description: 'Cy script content (or @filepath to read from .cy file)',
      required: true,
    }),
  }

  static override flags = {
    ...BaseCommand.baseFlags,
    data: Flags.string({
      description: 'JSON input data (or @filepath to read from file)',
    }),
    watch: Flags.boolean({
      description: 'Watch execution progress (default: true)',
      default: true,
      allowNo: true,
    }),
  }

  async run(): Promise<void> {
    const { args, flags } = await this.parse(TasksRunAdhoc)
    await this.initApi()

    const script = readScriptFlag(args.script)
    const inputData = flags.data ? parseDataFlag(flags.data as string) : undefined

    const body: Record<string, unknown> = { cy_script: script }
    if (inputData !== undefined) body.input = inputData

    const response = await this.client.request<RunResponse>(
      'POST',
      '/tasks/run',
      this.tenantId,
      { body },
    )

    const result = response.data

    // --no-watch or non-table output: print and exit
    if (!flags.watch || flags.output !== 'table') {
      const printOpts: PrintOptions = {
        format: flags.output as OutputFormat,
        fields: flags.fields ? (flags.fields as string).split(',').map((f) => f.trim()) : undefined,
        noHeader: flags['no-header'] as boolean,
      }

      printResponse(response, printOpts)
      return
    }

    // Live progress view
    console.log()
    console.log(chalk.bold('  Running ad-hoc script...'))
    console.log(chalk.dim(`  run: ${result.trid}`))
    console.log()

    const ok = await this.watchTaskRun(result.trid)
    if (!ok) this.exit(1)
  }

  private async watchTaskRun(trid: string): Promise<boolean> {
    const startTime = Date.now()
    const POLL_MS = 2000
    const TIMEOUT_MS = 10 * 60 * 1000

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
        console.log(`  ${chalk.green('✓')} Complete ${chalk.dim(`(${dur || el})`)}`)
        console.log()
        return true
      }

      if (taskRun.status === 'failed') {
        const el = elapsed(startTime)
        console.log()
        console.log(`  ${chalk.red('✗')} Failed ${chalk.dim(`(${el})`)}`)
        if (taskRun.error_message) {
          const firstLine = taskRun.error_message.split('\n')[0]
          console.log(`    ${chalk.dim(firstLine.slice(0, 120))}`)
        }

        console.log(chalk.dim(`\n  Details: analysi task-runs get ${trid.slice(0, 8)}... --output json`))
        console.log()
        return false
      }

      if (taskRun.status === 'paused') {
        const el = elapsed(startTime)
        console.log()
        console.log(`  ${chalk.yellow('⏸')} Paused — waiting for human input ${chalk.dim(`(${el})`)}`)
        console.log(chalk.dim(`  The script requires a human response before it can continue.`))
        console.log(chalk.dim(`  Check status: analysi task-runs get ${trid.slice(0, 8)}...`))
        console.log()
        return true
      }

      await sleep(POLL_MS)
    }

    console.log()
    console.log(chalk.yellow(`  ⚠ Timed out after ${elapsed(startTime)}. Task may still be running.`))
    console.log(chalk.dim(`  Check with: analysi task-runs get ${trid}`))
    console.log()
    return false
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
