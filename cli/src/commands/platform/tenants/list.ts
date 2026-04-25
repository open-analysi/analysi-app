/**
 * Platform tenants list command (Project Delos Phase 6).
 */

import { Command, Flags } from '@oclif/core'

import { ApiClient, ApiError } from '../../../lib/api-client.js'
import { loadCredentials } from '../../../lib/auth-manager.js'
import { EXIT } from '../../../lib/exit-codes.js'
import { printResponse, type OutputFormat, type PrintOptions } from '../../../lib/output.js'

export default class PlatformTenantsList extends Command {
  static override description = 'List all tenants'

  static override examples = [
    '<%= config.bin %> platform tenants list',
    '<%= config.bin %> platform tenants list --status active',
  ]

  static override flags = {
    status: Flags.string({ description: 'Filter by status (active, suspended)' }),
    'has-schedules': Flags.boolean({ description: 'Only tenants with enabled schedules' }),
    limit: Flags.integer({ default: 50, description: 'Max results' }),
    offset: Flags.integer({ default: 0, description: 'Offset' }),
    output: Flags.string({ char: 'o', options: ['table', 'json', 'csv'], default: 'table' }),
    fields: Flags.string({ description: 'Comma-separated fields' }),
    'no-header': Flags.boolean({ default: false }),
  }

  async run(): Promise<void> {
    const { flags } = await this.parse(PlatformTenantsList)

    const creds = loadCredentials()
    if (!creds?.api_key) {
      this.error('Not authenticated.', { exit: EXIT.USAGE_ERROR })
    }

    const client = new ApiClient(creds)

    try {
      const response = await client.requestPlatform('GET', '/tenants', {
        query: {
          status: flags.status,
          has_schedules: flags['has-schedules'] || undefined,
          limit: flags.limit,
          offset: flags.offset,
        },
      })

      const printOpts: PrintOptions = {
        format: flags.output as OutputFormat,
        fields: flags.fields ? flags.fields.split(',').map((f) => f.trim()) : undefined,
        noHeader: flags['no-header'],
      }

      printResponse(response, printOpts)
    } catch (error) {
      if (error instanceof ApiError) {
        this.error(error.message, { exit: EXIT.FAILURE })
      }
      throw error
    }
  }
}
