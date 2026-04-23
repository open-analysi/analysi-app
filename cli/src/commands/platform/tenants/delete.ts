/**
 * Platform tenant delete command (Project Delos Phase 6).
 */

import { Args, Command, Flags } from '@oclif/core'

import { ApiClient, ApiError } from '../../../lib/api-client.js'
import { loadCredentials } from '../../../lib/auth-manager.js'
import { EXIT } from '../../../lib/exit-codes.js'
import { printResponse, type OutputFormat, type PrintOptions } from '../../../lib/output.js'

export default class PlatformTenantsDelete extends Command {
  static override description = 'Delete a tenant and ALL its data (cascade delete)'

  static override examples = [
    '<%= config.bin %> platform tenants delete acme-corp --confirm acme-corp',
  ]

  static override args = {
    id: Args.string({ description: 'Tenant ID to delete', required: true }),
  }

  static override flags = {
    confirm: Flags.string({
      description: 'Safety confirmation — must match the tenant ID',
      required: true,
    }),
    output: Flags.string({ char: 'o', options: ['table', 'json', 'csv'], default: 'json' }),
  }

  async run(): Promise<void> {
    const { args, flags } = await this.parse(PlatformTenantsDelete)

    if (flags.confirm !== args.id) {
      this.error(`Confirmation mismatch: --confirm must match tenant ID '${args.id}'`, {
        exit: EXIT.USAGE_ERROR,
      })
    }

    const creds = loadCredentials()
    if (!creds?.api_key) {
      this.error('Not authenticated.', { exit: EXIT.USAGE_ERROR })
    }

    const client = new ApiClient(creds)

    try {
      const response = await client.requestPlatform('DELETE', `/tenants/${args.id}`, {
        query: { confirm: args.id },
      })
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
