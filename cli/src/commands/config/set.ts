/**
 * Set CLI configuration values.
 */

import { Args, Command } from '@oclif/core'
import chalk from 'chalk'

import { loadCredentials, saveCredentials } from '../../lib/auth-manager.js'

const ALLOWED_KEYS = ['default_tenant', 'base_url'] as const

export default class ConfigSet extends Command {
  static override description = 'Set a CLI configuration value'

  static override examples = [
    '<%= config.bin %> config set default_tenant acme-corp',
    '<%= config.bin %> config set base_url https://api.analysi.com',
  ]

  static override args = {
    key: Args.string({
      description: `Config key (${ALLOWED_KEYS.join(', ')})`,
      required: true,
      options: [...ALLOWED_KEYS],
    }),
    value: Args.string({
      description: 'Config value',
      required: true,
    }),
  }

  async run(): Promise<void> {
    const { args } = await this.parse(ConfigSet)

    const creds = loadCredentials()
    if (!creds?.api_key) {
      this.error('Not authenticated. Run `analysi auth login` first.', { exit: 1 })
    }

    const key = args.key as typeof ALLOWED_KEYS[number]
    const updated = { ...creds, [key]: args.value }
    saveCredentials(updated)

    console.log(`  ${chalk.green('✔')} Set ${chalk.cyan(key)} = ${chalk.bold(args.value)}`)
  }
}
