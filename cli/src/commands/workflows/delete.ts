/**
 * Hand-written workflow delete command with confirmation prompt.
 *
 * Asks for confirmation before deleting unless --yes is passed
 * or the command is running in a non-TTY environment.
 *
 * Uses direct client.request() instead of apiCall() because DELETE
 * returns 204 No Content ({data: null}), which the generic printResponse
 * pipeline can't render.
 */

import { Args, Flags } from '@oclif/core'
import chalk from 'chalk'

import { BaseCommand } from '../../base-command.js'
import { resolvePath } from '../../lib/config-loader.js'
import { printSuccess } from '../../lib/output.js'

export default class WorkflowsDelete extends BaseCommand {
  static override description = 'Delete a workflow (with confirmation)'

  static override examples = [
    '<%= config.bin %> workflows delete <workflow_id>',
    '<%= config.bin %> workflows delete <workflow_id> --yes',
  ]

  static override args = {
    workflow_id: Args.string({
      description: 'Workflow ID to delete',
      required: true,
    }),
  }

  static override flags = {
    ...BaseCommand.baseFlags,
  }

  async run(): Promise<void> {
    const { args, flags } = await this.parse(WorkflowsDelete)
    await this.initApi()

    // Confirm unless --yes or non-TTY
    if (!this.isNonInteractive(flags)) {
      const { confirm } = await import('@clack/prompts')
      const ok = await confirm({
        message: `Delete workflow ${args.workflow_id}? This cannot be undone.`,
      })

      if (!ok || typeof ok === 'symbol') {
        console.log(chalk.dim('  Cancelled'))
        return
      }
    }

    const resolvedPath = resolvePath('/workflows/{workflow_id}', args as Record<string, string>)

    // Call directly — DELETE returns 204 (null data), skip printResponse
    await this.client.request('DELETE', resolvedPath, this.tenantId)
    printSuccess(`Workflow ${args.workflow_id} deleted`)
  }
}
