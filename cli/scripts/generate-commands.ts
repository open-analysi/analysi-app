#!/usr/bin/env node

/**
 * Command Generator — reads cli-config.yaml and generates oclif command files.
 *
 * Usage: npm run generate
 *
 * This generates thin command files in src/commands/ that delegate to the
 * base command for API calls. Hand-written commands (auth/*, config/*) are
 * never overwritten.
 */

import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import yaml from 'js-yaml'

import type { CliConfig, FlagConfig, OperationConfig } from '../src/lib/types.js'

const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url))
const PROJECT_ROOT = join(SCRIPT_DIR, '..')
const CONFIG_PATH = join(PROJECT_ROOT, 'cli-config.yaml')
const COMMANDS_DIR = join(PROJECT_ROOT, 'src', 'commands')

// These directories contain hand-written commands — never overwrite
const PROTECTED_DIRS = new Set(['auth', 'config', 'packs', 'platform'])

// Individual hand-written command files — never overwrite (topic/command)
const PROTECTED_FILES = new Set([
  'alerts/analyze',
  'alerts/watch',
  'alerts/validate',
  'tasks/run',
  'tasks/run-adhoc',
  'tasks/create',
  'tasks/update',
  'tasks/compile',
  'workflows/run',
  'workflows/compose',
  'workflows/delete',
  'workflow-runs/watch',
  'integrations/run-tool',
  'tools/list',
  'tools/get',
  'skills/tree',
])

const GENERATED_HEADER = `/**
 * AUTO-GENERATED — DO NOT EDIT
 * Generated from cli-config.yaml by: npm run generate
 */`

function loadConfig(): CliConfig {
  const raw = readFileSync(CONFIG_PATH, 'utf-8')
  return yaml.load(raw) as CliConfig
}

function toClassName(topic: string, command: string): string {
  const pascal = (s: string) =>
    s
      .split(/[-_]/)
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join('')
  return `${pascal(topic)}${pascal(command)}`
}

function generateFlagDefinition(name: string, flag: FlagConfig): string {
  const parts: string[] = []

  if (flag.type === 'integer') {
    parts.push(`${name}: Flags.integer({`)
  } else if (flag.type === 'boolean') {
    parts.push(`${name}: Flags.boolean({`)
  } else {
    parts.push(`${name}: Flags.string({`)
  }

  parts.push(`      description: '${escapeString(flag.description)}',`)

  if (flag.required) {
    parts.push('      required: true,')
  }

  if (flag.default !== undefined) {
    parts.push(`      default: ${JSON.stringify(flag.default)},`)
  }

  if (flag.options) {
    parts.push(`      options: ${JSON.stringify(flag.options)},`)
  }

  parts.push('    })')
  return parts.join('\n')
}

function generateArgDefinition(name: string, arg: { required?: boolean; description: string }): string {
  return [
    `${name}: Args.string({`,
    `      description: '${escapeString(arg.description)}',`,
    arg.required ? '      required: true,' : '',
    '    })',
  ]
    .filter(Boolean)
    .join('\n')
}

function escapeString(s: string): string {
  return s.replace(/'/g, "\\'")
}

function generateExamples(topic: string, commandName: string, op: OperationConfig): string[] {
  const bin = '<%= config.bin %>'
  const base = `${bin} ${topic} ${commandName}`
  const examples: string[] = []

  // Build base example with required args
  const argPlaceholders = Object.entries(op.args ?? {})
    .map(([name]) => `<${name}>`)
    .join(' ')
  const baseExample = argPlaceholders ? `${base} ${argPlaceholders}` : base
  examples.push(baseExample)

  // Add a second example with a useful flag combination for list commands
  if (commandName === 'list' && op.flags) {
    const flagNames = Object.keys(op.flags)
    // Pick the first interesting filter flag (not limit/offset/sort/order)
    const filterFlag = flagNames.find((f) => !['limit', 'offset', 'sort', 'order', 'sort_by', 'sort_order'].includes(f))
    if (filterFlag) {
      const flagDef = op.flags[filterFlag]
      const sampleValue = flagDef.options?.[0] ?? (flagDef.type === 'boolean' ? '' : 'value')
      const flagStr = flagDef.type === 'boolean'
        ? `--${filterFlag}`
        : `--${filterFlag} ${sampleValue}`
      examples.push(`${base} ${flagStr} --limit 10`)
    }
  }

  // For get commands with args, add output json example
  if (argPlaceholders && ['get', 'health', 'status'].includes(commandName)) {
    examples.push(`${baseExample} --output json`)
  }

  return examples
}

function generateCommandFile(
  topic: string,
  commandName: string,
  op: OperationConfig,
): string {
  const className = toClassName(topic, commandName)
  const hasArgs = op.args && Object.keys(op.args).length > 0
  const hasFlags = op.flags && Object.keys(op.flags).length > 0

  const isWriteWithData = ['POST', 'PUT', 'PATCH'].includes(op.method) && op.flags?.data

  const imports = [`import { ${hasArgs ? 'Args, ' : ''}Flags } from '@oclif/core'`]
  // Calculate the relative path depth for imports
  const depth = topic.split('/').length
  const relPrefix = '../'.repeat(depth + 1)
  imports.push(`import { BaseCommand } from '${relPrefix}base-command.js'`)
  imports.push(`import { resolvePath } from '${relPrefix}lib/config-loader.js'`)
  if (isWriteWithData) {
    imports.push(`import { parseDataFlag } from '${relPrefix}lib/data-reader.js'`)
  }

  // Build args block
  const argsBlock = hasArgs
    ? `  static override args = {\n    ${Object.entries(op.args!)
        .map(([name, arg]) => generateArgDefinition(name, arg))
        .join(',\n    ')}\n  }\n`
    : ''

  // Build flags block
  const flagEntries = Object.entries(op.flags ?? {})
    .map(([name, flag]) => generateFlagDefinition(name, flag))
    .join(',\n    ')

  const flagsBlock = `  static override flags = {
    ...BaseCommand.baseFlags,${hasFlags ? `\n    ${flagEntries},` : ''}
  }\n`

  // Build run method
  const pathHasTemplateVars = op.path.includes('{')

  let resolvePathLine = ''
  if (pathHasTemplateVars && hasArgs) {
    resolvePathLine = `    const resolvedPath = resolvePath('${op.path}', args as Record<string, string>)\n`
  }

  const pathExpr = pathHasTemplateVars ? 'resolvedPath' : `'${op.path}'`

  // Separate flags into query params vs body data
  const isWriteMethod = ['POST', 'PUT', 'PATCH'].includes(op.method)
  const hasDataFlag = isWriteMethod && op.flags?.data

  // Query flags: all flags except 'data' for write methods
  const queryFlagNames = Object.keys(op.flags ?? {})
    .filter((name) => !(isWriteMethod && name === 'data'))
  let queryBlock = ''
  if (queryFlagNames.length > 0) {
    const entries = queryFlagNames
      .map((name) => `        ${name}: flags.${name}`)
      .join(',\n')
    queryBlock = `query: {\n${entries},\n      }`
  }

  // Body block for POST/PUT/PATCH with a 'data' flag
  // Supports @filepath syntax: --data @input.json reads from file
  let bodyBlock = ''
  if (hasDataFlag) {
    bodyBlock = 'body: flags.data ? parseDataFlag(flags.data as string) : undefined'
  }

  // Combine into options argument
  let optionsArg = ''
  if (queryBlock || bodyBlock) {
    const parts = [queryBlock, bodyBlock].filter(Boolean).join(',\n      ')
    optionsArg = `\n      { ${parts} },`
  }

  const runMethod = `  async run(): Promise<void> {
    const { args, flags } = await this.parse(${className})
    await this.initApi()
${resolvePathLine}
    await this.apiCall('${op.method}', ${pathExpr}${optionsArg ? `,${optionsArg.startsWith('\n') ? optionsArg : `\n      ${optionsArg}`}` : ''})
  }`

  // Build realistic examples
  const examples = generateExamples(topic, commandName, op)

  return `${GENERATED_HEADER}

${imports.join('\n')}

export default class ${className} extends BaseCommand {
  static override description = '${escapeString(op.description)}'

  static override examples = [
${examples.map((e) => `    '${escapeString(e)}',`).join('\n')}
  ]

${argsBlock}${flagsBlock}
${runMethod}
}
`
}

function main(): void {
  const config = loadConfig()
  let generated = 0
  let skipped = 0

  for (const [topic, topicConfig] of Object.entries(config.commands)) {
    if (PROTECTED_DIRS.has(topic)) {
      console.log(`  skip  ${topic}/ (hand-written)`)
      skipped++
      continue
    }

    const topicDir = join(COMMANDS_DIR, topic)
    if (!existsSync(topicDir)) {
      mkdirSync(topicDir, { recursive: true })
    }

    for (const [commandName, op] of Object.entries(topicConfig.operations)) {
      if (PROTECTED_FILES.has(`${topic}/${commandName}`)) {
        console.log(`  skip  ${topic}/${commandName}.ts (hand-written)`)
        skipped++
        continue
      }

      const filePath = join(topicDir, `${commandName}.ts`)
      const content = generateCommandFile(topic, commandName, op)
      writeFileSync(filePath, content)
      console.log(`  gen   ${topic}/${commandName}.ts`)
      generated++
    }
  }

  console.log(`\n  Done: ${generated} generated, ${skipped} skipped (hand-written)`)
}

main()
