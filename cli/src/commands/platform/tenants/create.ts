/**
 * Platform tenant create command (Project Delos Phase 6).
 */

import { Args, Flags } from '@oclif/core'
import { Command } from '@oclif/core'

import { ApiClient, ApiError } from '../../../lib/api-client.js'
import { loadCredentials } from '../../../lib/auth-manager.js'
import { EXIT } from '../../../lib/exit-codes.js'
import { printResponse, type OutputFormat, type PrintOptions } from '../../../lib/output.js'

export default class PlatformTenantsCreate extends Command {
  static override description = 'Create a new tenant'

  static override examples = [
    '<%= config.bin %> platform tenants create acme-corp --name "Acme Corp"',
    '<%= config.bin %> platform tenants create acme-corp --name "Acme Corp" --owner-email admin@acme.com',
    '<%= config.bin %> platform tenants create acme-corp --name "Acme Corp" --dry-run',
  ]

  static override args = {
    id: Args.string({ description: 'Tenant ID', required: true }),
  }

  static override flags = {
    name: Flags.string({ description: 'Display name', required: true }),
    'owner-email': Flags.string({ description: 'Email of the first tenant owner (creates user if needed)' }),
    'dry-run': Flags.boolean({ description: 'Validate only, do not create', default: false }),
    output: Flags.string({ char: 'o', options: ['table', 'json', 'csv'], default: 'table' }),
  }

  async run(): Promise<void> {
    const { args, flags } = await this.parse(PlatformTenantsCreate)

    const creds = loadCredentials()
    if (!creds?.api_key) {
      this.error('Not authenticated. Run `analysi auth login` first.', { exit: EXIT.USAGE_ERROR })
    }

    const client = new ApiClient(creds)

    try {
      const body: Record<string, string> = { id: args.id, name: flags.name }
      if (flags['owner-email']) {
        body.owner_email = flags['owner-email']
      }

      const response = await client.requestPlatform('POST', '/tenants', {
        query: { dry_run: flags['dry-run'] || undefined },
        body,
      })

      if (flags['dry-run']) {
        console.log(`✓ Tenant ID '${args.id}' is valid and available`)
      } else {
        const printOpts: PrintOptions = { format: flags.output as OutputFormat }
        printResponse(response, printOpts)
      }
    } catch (error) {
      if (error instanceof ApiError) {
        this.error(error.message, { exit: EXIT.FAILURE })
      }
      throw error
    }
  }
}
