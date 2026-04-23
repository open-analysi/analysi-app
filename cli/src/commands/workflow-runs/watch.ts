/**
 * Hand-written command to watch an already-running workflow execution.
 *
 * Polls the status and graph endpoints, showing node completions as they happen.
 * Useful when the workflow was started via the API, another session, or
 * you want to re-attach after disconnecting.
 */

import { Args } from '@oclif/core'
import chalk from 'chalk'

import { BaseCommand } from '../../base-command.js'
import { WorkflowProgressWatcher } from '../../lib/workflow-progress.js'

export default class WorkflowRunsWatch extends BaseCommand {
  static override description = 'Watch a running workflow execution'

  static override examples = [
    '<%= config.bin %> workflow-runs watch <workflow_run_id>',
  ]

  static override args = {
    workflow_run_id: Args.string({
      description: 'Workflow run ID to watch',
      required: true,
    }),
  }

  static override flags = {
    ...BaseCommand.baseFlags,
  }

  async run(): Promise<void> {
    const { args } = await this.parse(WorkflowRunsWatch)
    await this.initApi()

    const watcher = new WorkflowProgressWatcher(this.client, this.tenantId)
    const status = await watcher.getStatus(args.workflow_run_id)

    if (!status) {
      console.log()
      console.log(chalk.red(`  Workflow run not found: ${args.workflow_run_id.slice(0, 8)}...`))
      console.log()
      return
    }

    // Already terminal — show the result
    if (status.status === 'completed') {
      console.log()
      console.log(chalk.bold(`  Workflow run ${args.workflow_run_id.slice(0, 8)}...`))
      console.log(`  ${chalk.green('✓')} Already complete`)
      console.log()
      return
    }

    if (status.status === 'failed') {
      const detail = await watcher.getDetail(args.workflow_run_id)
      console.log()
      console.log(chalk.bold(`  Workflow run ${args.workflow_run_id.slice(0, 8)}...`))
      console.log(`  ${chalk.red('✗')} Already failed`)
      if (detail?.error_message) {
        console.log(`    ${chalk.dim(detail.error_message.split('\n')[0].slice(0, 120))}`)
      }

      console.log()
      return
    }

    if (status.status === 'cancelled') {
      console.log()
      console.log(chalk.bold(`  Workflow run ${args.workflow_run_id.slice(0, 8)}...`))
      console.log(`  ${chalk.yellow('⚠')} Already cancelled`)
      console.log()
      return
    }

    // In progress — attach and watch
    console.log()
    console.log(chalk.bold(`  Watching workflow run ${args.workflow_run_id.slice(0, 8)}...`))
    console.log(chalk.dim(`  status: ${status.status}`))
    console.log()

    await watcher.watch(args.workflow_run_id)
  }
}
