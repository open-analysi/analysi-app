/**
 * Hand-written packs list command (Project Delos Phase 5).
 *
 * Lists installed content packs for the current tenant.
 */

import { BaseCommand } from '../../base-command.js'
import type { OutputFormat, PrintOptions } from '../../lib/output.js'
import { printResponse } from '../../lib/output.js'

export default class PacksList extends BaseCommand {
  static override description = 'List installed content packs'

  static override examples = [
    '<%= config.bin %> packs list',
    '<%= config.bin %> packs list --output json',
  ]

  static override flags = {
    ...BaseCommand.baseFlags,
  }

  async run(): Promise<void> {
    const { flags } = await this.parse(PacksList)
    await this.initApi()

    const response = await this.client.request('GET', '/packs', this.tenantId)

    const printOpts: PrintOptions = {
      format: flags.output as OutputFormat,
      fields: flags.fields ? (flags.fields as string).split(',').map((f) => f.trim()) : undefined,
      noHeader: flags['no-header'] as boolean,
    }

    printResponse(response, printOpts)
  }
}
