/**
 * Base command for all Analysi CLI commands.
 * Handles authentication, API client setup, and output formatting.
 */

import { writeFileSync } from 'node:fs'

import { Command, Flags } from '@oclif/core'

import { ApiClient, ApiError } from './lib/api-client.js'
import { loadCredentials } from './lib/auth-manager.js'
import { EXIT, httpStatusToExitCode } from './lib/exit-codes.js'
import { printError, printResponse, type OutputFormat, type PrintOptions } from './lib/output.js'
import type { Credentials } from './lib/types.js'

export abstract class BaseCommand extends Command {
  static baseFlags = {
    tenant: Flags.string({
      char: 't',
      description: 'Tenant ID (overrides default from auth config)',
      env: 'ANALYSI_TENANT_ID',
    }),
    output: Flags.string({
      char: 'o',
      description: 'Output format',
      options: ['table', 'json', 'csv'],
      default: 'table',
    }),
    fields: Flags.string({
      description: 'Comma-separated list of fields to display (overrides defaults)',
    }),
    'no-header': Flags.boolean({
      description: 'Suppress table/CSV header row (useful for scripting)',
      default: false,
    }),
    out: Flags.string({
      description: 'Write output to a file instead of stdout',
    }),
    verbose: Flags.boolean({
      char: 'v',
      description: 'Show request details (URL, status, timing)',
      default: false,
    }),
    yes: Flags.boolean({
      char: 'y',
      description: 'Skip confirmation prompts (for automation/agents)',
      default: false,
    }),
  }

  /**
   * Check if running in non-interactive mode.
   * Returns true if --yes flag is set OR stdout is not a TTY.
   */
  protected isNonInteractive(flags: { yes?: boolean }): boolean {
    return flags.yes === true || !process.stdout.isTTY
  }

  protected credentials!: Credentials
  protected client!: ApiClient
  protected tenantId!: string

  /**
   * Initialize auth and API client.
   * Called by subclasses before making API requests.
   */
  protected async initApi(): Promise<void> {
    const creds = loadCredentials()
    if (!creds?.api_key) {
      this.error(
        'Not authenticated. Run `analysi auth login` first.',
        { exit: EXIT.USAGE_ERROR },
      )
    }

    this.credentials = creds

    const { flags } = await this.parse(this.constructor as typeof BaseCommand)
    this.tenantId = flags.tenant ?? creds.default_tenant ?? ''

    if (!this.tenantId) {
      this.error(
        'No tenant specified. Use --tenant or set a default with `analysi auth login`.',
        { exit: EXIT.USAGE_ERROR },
      )
    }

    this.client = new ApiClient(creds, 'v1')
  }

  /**
   * Make an API call and handle errors gracefully.
   */
  protected async apiCall<T = unknown>(
    method: string,
    path: string,
    options: {
      query?: Record<string, string | number | boolean | undefined>
      body?: unknown
    } = {},
  ): Promise<void> {
    const { flags } = await this.parse(this.constructor as typeof BaseCommand)
    const verbose = flags.verbose as boolean
    const outFile = flags.out as string | undefined

    const startTime = Date.now()

    try {
      if (verbose) {
        const fullPath = `/${this.client.apiVersion}/${this.tenantId}${path}`
        console.error(`  ${method} ${fullPath}`)
        if (options.query) {
          const defined = Object.entries(options.query).filter(([, v]) => v !== undefined)
          if (defined.length > 0) {
            console.error(`  query: ${JSON.stringify(Object.fromEntries(defined))}`)
          }
        }
      }

      const response = await this.client.request<T>(
        method,
        path,
        this.tenantId,
        options,
      )

      if (verbose) {
        const elapsed = Date.now() - startTime
        console.error(`  ${elapsed}ms`)
      }

      const printOpts: PrintOptions = {
        format: flags.output as OutputFormat,
        fields: flags.fields ? (flags.fields as string).split(',').map((f) => f.trim()) : undefined,
        noHeader: flags['no-header'] as boolean,
      }

      // If --out is specified, redirect stdout to file
      if (outFile) {
        const lines: string[] = []
        const origLog = console.log
        console.log = (...args: unknown[]) => lines.push(args.map(String).join(' '))
        printResponse(response, printOpts)
        console.log = origLog
        writeFileSync(outFile, lines.join('\n') + '\n')
        console.error(`  Written to ${outFile}`)
      } else {
        printResponse(response, printOpts)
      }
    } catch (error) {
      if (verbose) {
        const elapsed = Date.now() - startTime
        console.error(`  ${elapsed}ms`)
      }

      if (error instanceof ApiError) {
        printError(error.message)
        if (verbose) {
          console.error(`  HTTP ${error.statusCode}`)
        }

        this.exit(httpStatusToExitCode(error.statusCode))
      }

      // Handle network errors (connection refused, DNS failure, etc.)
      if (error instanceof TypeError || (error as NodeJS.ErrnoException).code === 'ECONNREFUSED') {
        const baseUrl = this.credentials?.base_url ?? 'the API server'
        printError(`Could not connect to ${baseUrl}`)
        console.error('  Is the API server running? Check your connection and try again.')
        this.exit(1)
      }

      throw error
    }
  }
}
