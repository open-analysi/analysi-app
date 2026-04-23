/**
 * Output formatting utilities for the Analysi CLI.
 * Tables, JSON, CSV, and colored output.
 */

import chalk from 'chalk'
import Table from 'cli-table3'

import type { ApiResponse } from './types.js'

export type OutputFormat = 'table' | 'json' | 'csv'

export interface PrintOptions {
  format: OutputFormat
  /** Override default column selection with specific field names */
  fields?: string[]
  /** Suppress header row in table/CSV output */
  noHeader?: boolean
}

/**
 * Format and print an API response.
 */
export function printResponse(
  response: ApiResponse,
  options: PrintOptions | OutputFormat = 'table',
): void {
  // Support legacy string-only call signature
  const opts: PrintOptions = typeof options === 'string'
    ? { format: options }
    : options

  const { data, meta } = response

  if (opts.format === 'json') {
    if (opts.fields && Array.isArray(data)) {
      console.log(JSON.stringify(
        (data as Record<string, unknown>[]).map((item) => pickFields(item, opts.fields!)),
        null, 2,
      ))
    } else if (opts.fields && !Array.isArray(data) && data) {
      console.log(JSON.stringify(pickFields(data as Record<string, unknown>, opts.fields), null, 2))
    } else {
      console.log(JSON.stringify(data, null, 2))
    }

    return
  }

  if (opts.format === 'csv') {
    if (Array.isArray(data) && data.length > 0) {
      printCsv(data as Record<string, unknown>[], opts)
    } else if (!Array.isArray(data) && data) {
      printCsv([data as Record<string, unknown>], opts)
    }

    return
  }

  // Table format
  if (!Array.isArray(data)) {
    printObject(data as Record<string, unknown>, opts)
    if (meta.request_id) {
      console.log(chalk.dim(`\n  request: ${meta.request_id}`))
    }

    return
  }

  if (data.length === 0) {
    console.log(chalk.dim('  No results found.'))
    console.log(chalk.dim('  Hint: try removing filters or increasing --limit'))
    return
  }

  printTable(data as Record<string, unknown>[], opts)

  // Print pagination info
  const parts: string[] = []
  if (meta.total !== undefined) parts.push(`${meta.total} total`)
  if (meta.limit !== undefined) parts.push(`limit: ${meta.limit}`)
  if (meta.offset !== undefined && meta.offset > 0) parts.push(`offset: ${meta.offset}`)
  if (parts.length > 0) {
    console.log(chalk.dim(`\n  ${parts.join(' | ')}`))
  }
}

/** Pick specific fields from an object */
function pickFields(obj: Record<string, unknown>, fields: string[]): Record<string, unknown> {
  const result: Record<string, unknown> = {}
  for (const f of fields) {
    if (f in obj) result[f] = obj[f]
  }

  return result
}

/**
 * Print a single object as formatted key-value pairs.
 * Large values (arrays, deep objects) are summarized to keep output readable.
 * Use --output json for full untruncated data.
 */
function printObject(obj: Record<string, unknown>, opts: PrintOptions): void {
  let entries = Object.entries(obj)
  if (entries.length === 0) return

  if (opts.fields) {
    entries = entries.filter(([key]) => opts.fields!.includes(key))
    if (entries.length === 0) return
  }

  const maxKeyLen = Math.max(...entries.map(([k]) => k.length))

  for (const [key, value] of entries) {
    const paddedKey = key.padEnd(maxKeyLen)
    const formattedValue = formatDetailValue(value)
    console.log(`  ${chalk.cyan(paddedKey)}  ${formattedValue}`)
  }
}

/**
 * Format a value for the detail (key-value) view.
 * Arrays are summarized as count; deep objects are truncated.
 */
function formatDetailValue(value: unknown): string {
  if (value === null || value === undefined) return chalk.dim('—')
  if (typeof value === 'boolean') return value ? chalk.green('true') : chalk.red('false')
  if (typeof value === 'number') return chalk.yellow(String(value))

  if (Array.isArray(value)) {
    if (value.length === 0) return chalk.dim('[]')
    // Show count + preview of first item
    const preview = typeof value[0] === 'object' && value[0] !== null
      ? JSON.stringify(value[0]).slice(0, 60) + '...'
      : String(value[0])
    return chalk.dim(`[${value.length} items] `) + chalk.dim(preview)
  }

  if (typeof value === 'object') {
    const json = JSON.stringify(value)
    if (json.length <= 120) return chalk.dim(json)
    return chalk.dim(json.slice(0, 117) + '...')
  }

  const str = String(value)
  // Show timestamps as relative time in detail view too
  if (isIsoTimestamp(str)) {
    return `${str} ${chalk.dim(`(${relativeTime(str)})`)}`
  }

  if (str.length <= 120) return str
  return str.slice(0, 117) + chalk.dim('...')
}

/**
 * Print an array of objects as a table.
 * Automatically picks columns from the first object.
 */
function printTable(items: Record<string, unknown>[], opts: PrintOptions): void {
  const allKeys = Object.keys(items[0])
  let columns: string[]

  if (opts.fields) {
    // User-specified fields — use exactly what they asked for
    columns = opts.fields.filter((k) => allKeys.includes(k))
  } else {
    // Auto-select: priority keys first, skip noisy ones, max 8
    const priorityKeys = [
      'id', 'alert_id', 'human_readable_id', 'integration_id',
      'name', 'title', 'task_name', 'workflow_name',
      'status', 'analysis_status',
      'severity', 'type', 'enabled',
      'created_at', 'updated_at',
    ]

    const skipKeys = new Set([
      'tenant_id', 'raw_alert', 'risk_entities', 'iocs', 'script',
      'data_samples', 'io_schema', 'content_hash', 'current_analysis',
      'input_data', 'output_data', 'execution_context', 'executor_config',
      'cy_script', 'llm_usage', 'llm_config',
    ])

    const filteredKeys = allKeys.filter((k) => !skipKeys.has(k))
    columns = [
      ...priorityKeys.filter((k) => filteredKeys.includes(k)),
      ...filteredKeys.filter((k) => !priorityKeys.includes(k)),
    ].slice(0, 8)
  }

  if (columns.length === 0) return

  const table = new Table({
    head: opts.noHeader ? [] : columns.map((c) => chalk.bold.white(c)),
    style: {
      head: [],
      border: ['dim'],
    },
    chars: {
      top: '─', 'top-mid': '┬', 'top-left': '┌', 'top-right': '┐',
      bottom: '─', 'bottom-mid': '┴', 'bottom-left': '└', 'bottom-right': '┘',
      left: '│', 'left-mid': '├', mid: '─', 'mid-mid': '┼',
      right: '│', 'right-mid': '┤', middle: '│',
    },
  })

  for (const item of items) {
    table.push(columns.map((col) => truncate(formatValue(item[col]), 40)))
  }

  console.log(table.toString())
}

/**
 * Format a value for table display.
 * Timestamps are shown as relative time (e.g. "3m ago").
 * Status values are colorized for quick visual scanning.
 */
function formatValue(value: unknown): string {
  if (value === null || value === undefined) return chalk.dim('—')
  if (typeof value === 'boolean') return value ? chalk.green('true') : chalk.red('false')
  if (typeof value === 'number') return chalk.yellow(String(value))
  if (typeof value === 'object') return chalk.dim(JSON.stringify(value))

  const str = String(value)
  if (isIsoTimestamp(str)) {
    return chalk.dim(relativeTime(str))
  }

  // Colorize known status values
  const statusColor = STATUS_COLORS[str.toLowerCase()]
  if (statusColor) return statusColor(str)

  // Colorize severity values
  const sevColor = SEVERITY_COLORS[str.toLowerCase()]
  if (sevColor) return sevColor(str)

  return str
}

/** Status value color map */
const STATUS_COLORS: Record<string, (s: string) => string> = {
  completed: chalk.green,
  healthy: chalk.green,
  running: chalk.yellow,
  analyzing: chalk.yellow,
  pending: chalk.yellow,
  failed: chalk.red,
  unhealthy: chalk.red,
  cancelled: chalk.dim,
}

/** Severity value color map */
const SEVERITY_COLORS: Record<string, (s: string) => string> = {
  critical: chalk.red.bold,
  high: chalk.red,
  medium: chalk.yellow,
  low: chalk.blue,
  informational: chalk.dim,
}

/** Check if a string looks like an ISO 8601 timestamp */
function isIsoTimestamp(str: string): boolean {
  // Match patterns like 2026-03-12T08:14:22Z or 2026-03-12T08:14:22.331330Z
  return /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/.test(str)
}

/** Convert an ISO timestamp to a human-friendly relative time */
function relativeTime(iso: string): string {
  const then = new Date(iso).getTime()
  const now = Date.now()
  const diffMs = now - then

  if (Number.isNaN(then)) return iso

  const absDiff = Math.abs(diffMs)
  const suffix = diffMs >= 0 ? 'ago' : 'from now'

  if (absDiff < 60_000) return 'just now'
  if (absDiff < 3_600_000) return `${Math.floor(absDiff / 60_000)}m ${suffix}`
  if (absDiff < 86_400_000) return `${Math.floor(absDiff / 3_600_000)}h ${suffix}`
  if (absDiff < 604_800_000) return `${Math.floor(absDiff / 86_400_000)}d ${suffix}`

  // Older than a week — show the date
  return new Date(iso).toLocaleDateString()
}

/**
 * Truncate a string to a max length (ANSI-aware).
 * Strips ANSI codes, truncates the plain text, then re-applies dim for ellipsis.
 */
function truncate(str: string, max: number): string {
  // eslint-disable-next-line no-control-regex
  const plain = str.replace(/\u001B\[\d+(?:;\d+)*m/g, '')
  if (plain.length <= max) return str
  // Truncate the plain text to avoid cutting inside ANSI escape sequences
  return plain.slice(0, max - 1) + chalk.dim('...')
}

/**
 * Print an array of objects as CSV.
 * Handles quoting for values containing commas, quotes, or newlines.
 */
function printCsv(items: Record<string, unknown>[], opts: PrintOptions): void {
  let columns: string[]
  if (opts.fields) {
    columns = opts.fields.filter((k) => k in items[0])
  } else {
    columns = Object.keys(items[0])
  }

  const escapeCsv = (val: unknown): string => {
    if (val === null || val === undefined) return ''
    const str = typeof val === 'object' ? JSON.stringify(val) : String(val)
    if (str.includes(',') || str.includes('"') || str.includes('\n')) {
      return `"${str.replace(/"/g, '""')}"`
    }

    return str
  }

  if (!opts.noHeader) {
    console.log(columns.join(','))
  }

  for (const item of items) {
    console.log(columns.map((col) => escapeCsv(item[col])).join(','))
  }
}

/**
 * Print a styled error message.
 */
export function printError(message: string): void {
  console.error(`  ${chalk.red.bold('Error')} ${message}`)
}

/**
 * Print a styled success message.
 */
export function printSuccess(message: string): void {
  console.log(`  ${chalk.green('✔')} ${message}`)
}

/**
 * Print a styled warning message.
 */
export function printWarning(message: string): void {
  console.log(`  ${chalk.yellow('⚠')} ${message}`)
}
