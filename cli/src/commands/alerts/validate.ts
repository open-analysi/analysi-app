/**
 * Hand-written alert validation command.
 *
 * Validates alert JSON against the alert schema.
 * Falls back to client-side validation if no server endpoint exists.
 */

import { Flags } from '@oclif/core'
import chalk from 'chalk'

import { BaseCommand } from '../../base-command.js'
import { parseDataFlag } from '../../lib/data-reader.js'
import { validateAlert, type ValidationResult } from '../../lib/alert-validator.js'

export default class AlertsValidate extends BaseCommand {
  static override description = 'Validate alert JSON against the alert schema'

  static override examples = [
    '<%= config.bin %> alerts validate --data @alert.json',
    '<%= config.bin %> alerts validate --data \'{"title": "Test", "severity": "high", "triggering_event_time": "2026-01-01T00:00:00Z", "raw_alert": "..."}\'',
    '<%= config.bin %> alerts validate --data @alert.json --output json',
  ]

  static override flags = {
    ...BaseCommand.baseFlags,
    data: Flags.string({
      description: 'Alert JSON to validate (or @filepath to read from file)',
      required: true,
    }),
  }

  async run(): Promise<void> {
    const { flags } = await this.parse(AlertsValidate)

    const alertData = parseDataFlag(flags.data as string) as Record<string, unknown>

    // Client-side validation against the alert schema
    const result: ValidationResult = validateAlert(alertData)

    // JSON output
    if (flags.output === 'json') {
      console.log(JSON.stringify(result, null, 2))
      if (!result.valid) this.exit(1)
      return
    }

    // CSV output
    if (flags.output === 'csv') {
      const rows = [
        ...result.errors.map((e) => ({ ...e, level: 'error' })),
        ...result.warnings.map((w) => ({ ...w, level: 'warning' })),
      ]
      if (rows.length > 0) {
        if (!flags['no-header']) console.log('level,field,error_type,message')
        for (const r of rows) {
          console.log(`${r.level},${r.field},${r.error_type},"${r.message}"`)
        }
      }

      if (!result.valid) this.exit(1)
      return
    }

    // Pretty-print validation results
    console.log()
    if (result.valid) {
      console.log(`  ${chalk.green('✓')} Alert is valid`)
      console.log(chalk.dim(`  ${result.alert_structure.field_count} fields`))
    } else {
      console.log(`  ${chalk.red('✗')} Validation failed`)
    }

    if (result.errors.length > 0) {
      console.log()
      console.log(chalk.red.bold('  Errors:'))
      for (const err of result.errors) {
        console.log(`    ${chalk.red('•')} ${chalk.bold(err.field)}: ${err.message}`)
      }
    }

    if (result.warnings.length > 0) {
      console.log()
      console.log(chalk.yellow.bold('  Warnings:'))
      for (const warn of result.warnings) {
        console.log(`    ${chalk.yellow('•')} ${chalk.bold(warn.field)}: ${warn.message}`)
      }
    }

    console.log()

    if (!result.valid) this.exit(1)
  }
}
