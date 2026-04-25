/**
 * Hand-written describe command — runtime schema introspection.
 *
 * Returns a JSON Schema-like description of a command's inputs (args, flags)
 * and metadata. Agents call this to understand exactly how to invoke a command
 * without parsing --help text.
 *
 * Usage:
 *   analysi describe tasks create
 *   analysi describe workflows run
 *   analysi describe alerts list
 */

import { Args, Command } from '@oclif/core'

export default class Describe extends Command {
  static override description = 'Describe a command\'s arguments, flags, and usage as JSON (for agent/script consumption)'

  static override examples = [
    '<%= config.bin %> describe tasks create',
    '<%= config.bin %> describe alerts list',
    '<%= config.bin %> describe workflows run',
  ]

  // Strict false to capture variadic topic + command words
  static override strict = false

  static override args = {
    command: Args.string({
      description: 'Command to describe (e.g. "tasks create" or "tasks:create")',
      required: true,
    }),
  }

  async run(): Promise<void> {
    const { argv } = await this.parse(Describe)

    // Join all args into a command ID (support both "tasks create" and "tasks:create")
    const words = argv as string[]
    const commandId = words.join(' ').replace(/ /g, ':')

    const cmd = this.config.commands.find(
      (c) => c.id === commandId || c.id === words.join(':'),
    )

    if (!cmd) {
      const available = this.config.commands
        .filter((c) => !['list-commands', 'describe', 'autocomplete', 'help'].includes(c.id))
        .map((c) => c.id.replace(/:/g, ' '))
        .sort()

      console.error(JSON.stringify({
        error: `Command "${words.join(' ')}" not found`,
        available_commands: available,
      }, null, 2))
      this.exit(1)
    }

    // Build detailed schema
    const schema = buildCommandSchema(cmd)
    console.log(JSON.stringify(schema, null, 2))
  }
}

interface OclifFlag {
  type: string
  required?: boolean
  description?: string
  options?: string[]
  default?: unknown
  char?: string
  allowNo?: boolean
}

interface OclifArg {
  name: string
  required?: boolean
  description?: string
}

function buildCommandSchema(cmd: {
  id: string
  description?: string
  args?: Record<string, unknown>
  flags?: Record<string, unknown>
  examples?: Array<string | { command: string; description: string }>
  strict?: boolean
}) {
  const command = cmd.id.replace(/:/g, ' ')

  // Build args schema
  const args: Record<string, unknown> = {}
  const requiredArgs: string[] = []

  for (const [name, rawArg] of Object.entries(cmd.args ?? {})) {
    const arg = rawArg as OclifArg
    args[name] = {
      type: 'string',
      description: arg.description ?? '',
    }

    if (arg.required) requiredArgs.push(name)
  }

  // Build flags schema — split into command-specific and base
  const properties: Record<string, unknown> = {}
  const required: string[] = []

  const BASE_FLAGS = new Set([
    'tenant', 'output', 'fields', 'no-header', 'out', 'verbose',
  ])

  // oclif metadata doesn't distinguish integer from string (both are type: "option").
  // Detect via numeric default OR known integer flag names from our codebase.
  const KNOWN_INTEGER_FLAGS = new Set(['limit', 'offset', 'timeout', 'example'])

  for (const [name, rawFlag] of Object.entries(cmd.flags ?? {})) {
    if (BASE_FLAGS.has(name)) continue

    const flag = rawFlag as OclifFlag
    const prop: Record<string, unknown> = {
      description: flag.description ?? '',
    }

    if (flag.type === 'boolean') {
      prop.type = 'boolean'
      if (flag.default !== undefined) prop.default = flag.default
    } else if (typeof flag.default === 'number' || KNOWN_INTEGER_FLAGS.has(name)) {
      prop.type = 'integer'
      if (flag.default !== undefined) prop.default = flag.default
      if (flag.options) prop.enum = flag.options
    } else {
      prop.type = 'string'
      if (flag.options) prop.enum = flag.options
      if (flag.default !== undefined) prop.default = flag.default
    }

    if (flag.char) prop.short = flag.char

    properties[name] = prop
    if (flag.required) required.push(name)
  }

  // Build example invocations (strip oclif template variables)
  const examples = (cmd.examples ?? []).map((ex) => {
    if (typeof ex === 'string') {
      return ex.replace(/<%= config\.bin %>/g, 'analysi')
    }

    // Object-form example: { command: '...', description: '...' }
    if (typeof ex === 'object' && ex.command) {
      return ex.command.replace(/<%= config\.bin %>/g, 'analysi')
    }

    return String(ex)
  })

  return {
    command,
    description: cmd.description ?? '',
    usage: `analysi ${command}`,
    arguments: Object.keys(args).length > 0 ? {
      type: 'object',
      properties: args,
      required: requiredArgs.length > 0 ? requiredArgs : undefined,
    } : undefined,
    flags: Object.keys(properties).length > 0 ? {
      type: 'object',
      properties,
      required: required.length > 0 ? required : undefined,
    } : undefined,
    base_flags: 'All commands accept: --tenant (-t), --output (-o) [table|json|csv], --fields, --no-header, --out, --verbose (-v)',
    examples: examples.length > 0 ? examples : undefined,
    accepts_variadic: cmd.strict === false ? true : undefined,
  }
}
