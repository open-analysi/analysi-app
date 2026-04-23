/**
 * Platform health command (Project Delos Phase 6).
 */

import { Command, Flags } from '@oclif/core'

import { ApiClient, ApiError } from '../../lib/api-client.js'
import { loadCredentials } from '../../lib/auth-manager.js'
import { EXIT } from '../../lib/exit-codes.js'
import { printResponse, type OutputFormat, type PrintOptions } from '../../lib/output.js'

export default class PlatformHealth extends Command {
  static override description = 'Check platform database health'

  static override examples = ['<%= config.bin %> platform health']

  static override flags = {
    output: Flags.string({ char: 'o', options: ['table', 'json', 'csv'], default: 'json' }),
  }

  async run(): Promise<void> {
    const { flags } = await this.parse(PlatformHealth)

    const creds = loadCredentials()
    if (!creds?.api_key) {
      this.error('Not authenticated.', { exit: EXIT.USAGE_ERROR })
    }

    const client = new ApiClient(creds)

    try {
      const response = await client.requestPlatform('GET', '/health/db')
      const printOpts: PrintOptions = { format: flags.output as OutputFormat }
      printResponse(response, printOpts)
    } catch (error) {
      if (error instanceof ApiError) {
        this.error(error.message, { exit: EXIT.FAILURE })
      }
      throw error
    }
  }
}
