/**
 * Show current authentication status.
 */

import { Command } from '@oclif/core'
import chalk from 'chalk'

import {
  getCredentialsPath,
  loadCredentials,
} from '../../lib/auth-manager.js'

export default class Status extends Command {
  static override description = 'Show current authentication status'
  static override examples = ['<%= config.bin %> auth status']

  async run(): Promise<void> {
    const creds = loadCredentials()

    if (!creds?.api_key) {
      console.log(`  ${chalk.red('Not authenticated')}`)
      console.log(`  Run ${chalk.cyan('analysi auth login')} to get started.`)
      return
    }

    const masked = creds.api_key.slice(0, 8) + '...' + creds.api_key.slice(-4)

    console.log('')
    console.log(`  ${chalk.bold('Analysi CLI — Auth Status')}`)
    console.log('')
    console.log(`  ${chalk.cyan('API Key')}      ${masked}`)
    console.log(`  ${chalk.cyan('Base URL')}     ${creds.base_url}`)
    console.log(`  ${chalk.cyan('Tenant')}       ${creds.default_tenant ?? chalk.dim('not set')}`)
    console.log(`  ${chalk.cyan('Config')}       ${getCredentialsPath()}`)
    console.log('')
  }
}
