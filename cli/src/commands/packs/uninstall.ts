/**
 * Hand-written packs uninstall command (Project Delos Phase 5).
 *
 * Removes all components and workflows tagged with a pack's app name.
 */

import { Args, Flags } from '@oclif/core'

import { BaseCommand } from '../../base-command.js'
import type { OutputFormat, PrintOptions } from '../../lib/output.js'
import { printResponse } from '../../lib/output.js'

export default class PacksUninstall extends BaseCommand {
  static override description = 'Uninstall a content pack'

  static override examples = [
    '<%= config.bin %> packs uninstall examples',
    '<%= config.bin %> packs uninstall examples --force',
  ]

  static override args = {
    name: Args.string({
      description: 'Pack name to uninstall',
      required: true,
    }),
  }

  static override flags = {
    ...BaseCommand.baseFlags,
    force: Flags.boolean({
      description: 'Force uninstall even if components were modified by users',
      default: false,
    }),
  }

  async run(): Promise<void> {
    const { args, flags } = await this.parse(PacksUninstall)
    await this.initApi()

    const response = await this.client.request(
      'DELETE',
      `/packs/${args.name}`,
      this.tenantId,
      { query: { force: flags.force || undefined } },
    )

    const printOpts: PrintOptions = {
      format: flags.output as OutputFormat,
      fields: flags.fields ? (flags.fields as string).split(',').map((f) => f.trim()) : undefined,
      noHeader: flags['no-header'] as boolean,
    }

    printResponse(response, printOpts)
  }
}
