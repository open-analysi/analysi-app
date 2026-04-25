/**
 * Platform tenant describe command (Project Delos Phase 6).
 */

import { Args, Command, Flags } from '@oclif/core'

import { ApiClient, ApiError } from '../../../lib/api-client.js'
import { loadCredentials } from '../../../lib/auth-manager.js'
import { EXIT } from '../../../lib/exit-codes.js'
import { printResponse, type OutputFormat, type PrintOptions } from '../../../lib/output.js'

export default class PlatformTenantsDescribe extends Command {
  static override description = 'Describe a tenant (metadata, members, component counts, installed packs)'

  static override examples = [
    '<%= config.bin %> platform tenants describe acme-corp',
  ]

  static override args = {
    id: Args.string({ description: 'Tenant ID', required: true }),
  }

  static override flags = {
    output: Flags.string({ char: 'o', options: ['table', 'json', 'csv'], default: 'json' }),
  }

  async run(): Promise<void> {
    const { args, flags } = await this.parse(PlatformTenantsDescribe)

    const creds = loadCredentials()
    if (!creds?.api_key) {
      this.error('Not authenticated.', { exit: EXIT.USAGE_ERROR })
    }

    const client = new ApiClient(creds)

    try {
      const response = await client.requestPlatform('GET', `/tenants/${args.id}`)
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
