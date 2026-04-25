/**
 * AUTO-GENERATED — DO NOT EDIT
 * Generated from cli-config.yaml by: npm run generate
 */

import { Flags } from '@oclif/core'
import { BaseCommand } from '../../base-command.js'
import { resolvePath } from '../../lib/config-loader.js'

export default class AlertsList extends BaseCommand {
  static override description = 'List alerts with optional filters'

  static override examples = [
    '<%= config.bin %> alerts list',
    '<%= config.bin %> alerts list --status value --limit 10',
  ]

  static override flags = {
    ...BaseCommand.baseFlags,
    status: Flags.string({
      description: 'Filter by analysis status',
    }),
    severity: Flags.string({
      description: 'Filter by severity',
    }),
    source_vendor: Flags.string({
      description: 'Filter by source vendor (e.g. Splunk)',
    }),
    source_product: Flags.string({
      description: 'Filter by source product',
    }),
    disposition_category: Flags.string({
      description: 'Filter by disposition category',
    }),
    sort_by: Flags.string({
      description: 'Sort field',
      options: ["human_readable_id","title","severity","analysis_status","triggering_event_time","created_at","updated_at"],
    }),
    sort_order: Flags.string({
      description: 'Sort order (asc, desc)',
      options: ["asc","desc"],
    }),
    include_short_summary: Flags.boolean({
      description: 'Include short summary in results',
    }),
    limit: Flags.integer({
      description: 'Maximum number of results',
      default: 25,
    }),
    offset: Flags.integer({
      description: 'Offset for pagination',
      default: 0,
    }),
  }

  async run(): Promise<void> {
    const { args, flags } = await this.parse(AlertsList)
    await this.initApi()

    await this.apiCall('GET', '/alerts',
      { query: {
        status: flags.status,
        severity: flags.severity,
        source_vendor: flags.source_vendor,
        source_product: flags.source_product,
        disposition_category: flags.disposition_category,
        sort_by: flags.sort_by,
        sort_order: flags.sort_order,
        include_short_summary: flags.include_short_summary,
        limit: flags.limit,
        offset: flags.offset,
      } },)
  }
}
