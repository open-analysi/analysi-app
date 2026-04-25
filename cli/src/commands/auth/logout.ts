/**
 * Logout command — clears stored credentials.
 */

import { Command } from '@oclif/core'
import * as p from '@clack/prompts'
import chalk from 'chalk'

import {
  clearCredentials,
  getCredentialsPath,
  loadCredentials,
} from '../../lib/auth-manager.js'

export default class Logout extends Command {
  static override description = 'Clear stored credentials'
  static override examples = ['<%= config.bin %> auth logout']

  async run(): Promise<void> {
    const creds = loadCredentials()

    if (!creds?.api_key) {
      p.log.info('Not currently authenticated.')
      return
    }

    const confirm = await p.confirm({
      message: `Clear credentials for ${chalk.cyan(creds.default_tenant ?? 'unknown tenant')}?`,
    })

    if (p.isCancel(confirm) || !confirm) {
      p.log.info('Logout cancelled.')
      return
    }

    clearCredentials()
    p.log.success(`Credentials cleared from ${chalk.dim(getCredentialsPath())}`)
  }
}
