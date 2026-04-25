/**
 * Interactive login command with @clack/prompts.
 */

import { Command } from '@oclif/core'
import * as p from '@clack/prompts'
import chalk from 'chalk'

import { loadCredentials, saveCredentials } from '../../lib/auth-manager.js'

export default class Login extends Command {
  static override description = 'Authenticate with the Analysi platform'
  static override examples = ['<%= config.bin %> auth login']

  async run(): Promise<void> {
    p.intro(chalk.bgCyan.black(' Analysi CLI — Login '))

    const existing = loadCredentials()

    const baseUrl = await p.text({
      message: 'API base URL',
      placeholder: 'http://localhost:8001',
      initialValue: existing?.base_url ?? 'http://localhost:8001',
      validate: (v) => {
        try {
          new URL(v)
        } catch {
          return 'Must be a valid URL'
        }
      },
    })

    if (p.isCancel(baseUrl)) {
      p.cancel('Login cancelled.')
      this.exit(0)
    }

    const apiKey = await p.password({
      message: 'API key',
      validate: (v) => {
        if (!v || v.trim().length === 0) return 'API key is required'
      },
    })

    if (p.isCancel(apiKey)) {
      p.cancel('Login cancelled.')
      this.exit(0)
    }

    // Verify credentials by hitting the API root
    const spin = p.spinner()
    spin.start('Verifying credentials...')

    try {
      // Test connectivity via the health endpoint
      const response = await fetch(`${baseUrl}/health`, {
        headers: { 'X-API-Key': apiKey },
      })

      if (!response.ok) {
        spin.stop('Verification failed')
        const detail = response.status === 401
          ? 'Invalid API key. Please check and try again.'
          : `API returned HTTP ${response.status}. Check the base URL and API key.`
        p.log.error(chalk.red(detail))
        this.exit(1)
      }

      spin.stop('Credentials verified')
    } catch (error) {
      spin.stop('Connection failed')
      p.log.error(
        chalk.red(`Could not connect to ${baseUrl}. Is the API server running?`),
      )
      this.exit(1)
    }

    const tenant = await p.text({
      message: 'Default tenant ID',
      placeholder: 'my-tenant',
      initialValue: existing?.default_tenant ?? '',
      validate: (v) => {
        if (!v || v.trim().length === 0) return 'Tenant ID is required'
      },
    })

    if (p.isCancel(tenant)) {
      p.cancel('Login cancelled.')
      this.exit(0)
    }

    // Save credentials
    saveCredentials({
      api_key: apiKey,
      base_url: baseUrl,
      default_tenant: tenant,
    })

    p.log.success(chalk.green('Credentials saved'))

    // Offer shell completions
    const completions = await p.confirm({
      message: 'Set up shell completions?',
      initialValue: false,
    })

    if (!p.isCancel(completions) && completions) {
      const shell = await p.select({
        message: 'Which shell?',
        options: [
          { value: 'zsh', label: 'zsh' },
          { value: 'bash', label: 'bash' },
          { value: 'fish', label: 'fish' },
        ],
      })

      if (!p.isCancel(shell)) {
        const { execSync } = await import('node:child_process')
        try {
          // Generate the autocomplete cache
          execSync(`analysi autocomplete ${shell}`, { stdio: 'ignore' })

          // Get the setup script line
          const scriptLine = execSync(`analysi autocomplete script ${shell}`, {
            encoding: 'utf-8',
          }).trim()

          // Determine the rc file
          const rcFile = shell === 'zsh' ? '~/.zshrc' : shell === 'bash' ? '~/.bashrc' : '~/.config/fish/config.fish'

          p.note(
            `Add this line to ${chalk.cyan(rcFile)}:\n\n  ${chalk.cyan(scriptLine)}\n\nThen reload your shell:\n\n  ${chalk.cyan(`source ${rcFile}`)}`,
            'Shell Completions',
          )
        } catch {
          p.log.warning('Could not generate completions. Run manually: ' + chalk.cyan(`analysi autocomplete ${shell}`))
        }
      }
    }

    p.outro(chalk.green(`Logged in — default tenant: ${chalk.bold(tenant)}`))
  }
}
