/**
 * Hand-written list-commands — agent-friendly command index.
 *
 * Returns a compact JSON array of all CLI commands with descriptions,
 * args, and flag summaries. Designed for progressive disclosure:
 * agents load this once, then drill into specific commands via `describe`.
 *
 * Base flags (--tenant, --output, --fields, --verbose, etc.) are omitted
 * from the per-command flag list since they're shared across all commands.
 */

import { Command, Flags } from '@oclif/core'

const BASE_FLAGS = new Set([
  'tenant', 'output', 'fields', 'no-header', 'out', 'verbose',
])

// oclif metadata doesn't distinguish integer from string (both are type: "option").
// Detect via numeric default OR known integer flag names from our codebase.
const KNOWN_INTEGER_FLAGS = new Set(['limit', 'offset', 'timeout', 'example'])

export default class ListCommands extends Command {
  static override description = 'List all CLI commands as JSON (for agent/script consumption)'

  static override examples = [
    '<%= config.bin %> list-commands',
    '<%= config.bin %> list-commands | jq ".[].command"',
  ]

  static override flags = {
    'include-base-flags': Flags.boolean({
      description: 'Include shared base flags (tenant, output, verbose, etc.) in each command',
      default: false,
    }),
  }

  async run(): Promise<void> {
    const { flags } = await this.parse(ListCommands)
    const includeBase = flags['include-base-flags']

    const commands = this.config.commands
      .filter((cmd) => !['list-commands', 'describe', 'autocomplete', 'help'].includes(cmd.id))
      .sort((a, b) => a.id.localeCompare(b.id))
      .map((cmd) => {
        // Convert oclif topic:separator to space-separated
        const command = cmd.id.replace(/:/g, ' ')

        // Build args summary
        const args = Object.entries(cmd.args ?? {}).map(([name, arg]) => ({
          name,
          required: (arg as { required?: boolean }).required ?? false,
          description: (arg as { description?: string }).description ?? '',
        }))

        // Build flags summary (exclude base flags unless requested)
        const flagEntries = Object.entries(cmd.flags ?? {})
          .filter(([name]) => includeBase || !BASE_FLAGS.has(name))

        const cmdFlags = flagEntries.map(([name, flag]) => {
          const f = flag as {
            type: string
            required?: boolean
            description?: string
            options?: string[]
            default?: unknown
          }
          const flagType = f.type === 'boolean' ? 'boolean'
            : (typeof f.default === 'number' || KNOWN_INTEGER_FLAGS.has(name)) ? 'integer'
            : 'string'
          const entry: Record<string, unknown> = {
            name,
            type: flagType,
            required: f.required ?? false,
          }

          if (f.description) entry.description = f.description
          if (f.options) entry.options = f.options
          if (f.default !== undefined) entry.default = f.default
          return entry
        })

        return {
          command,
          description: cmd.description ?? '',
          args: args.length > 0 ? args : undefined,
          flags: cmdFlags.length > 0 ? cmdFlags : undefined,
        }
      })

    console.log(JSON.stringify(commands, null, 2))
  }
}
