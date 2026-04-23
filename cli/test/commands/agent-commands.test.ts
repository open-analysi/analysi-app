/**
 * Tests for agent-friendly commands: list-commands and describe.
 *
 * These tests verify the introspection commands produce valid JSON
 * with the expected structure for agent consumption.
 */

import { readFileSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, it, expect } from 'vitest'

const CLI_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..')
const COMMANDS_DIR = join(CLI_ROOT, 'src', 'commands')

describe('list-commands.ts', () => {
  const src = readFileSync(join(COMMANDS_DIR, 'list-commands.ts'), 'utf-8')

  it('does NOT extend BaseCommand (standalone, no auth needed)', () => {
    expect(src).toContain('extends Command')
    expect(src).not.toContain('extends BaseCommand')
  })

  it('filters out introspection commands from output', () => {
    expect(src).toContain("'list-commands'")
    expect(src).toContain("'describe'")
    expect(src).toContain("'autocomplete'")
    expect(src).toContain("'help'")
  })

  it('omits base flags by default', () => {
    expect(src).toContain('BASE_FLAGS')
    expect(src).toContain("'include-base-flags'")
  })

  it('converts colon-separated IDs to space-separated', () => {
    expect(src).toContain("replace(/:/g, ' ')")
  })

  it('outputs JSON to stdout', () => {
    expect(src).toContain('JSON.stringify')
  })
})

describe('describe.ts', () => {
  const src = readFileSync(join(COMMANDS_DIR, 'describe.ts'), 'utf-8')

  it('does NOT extend BaseCommand (standalone, no auth needed)', () => {
    expect(src).toContain('extends Command')
    expect(src).not.toContain('extends BaseCommand')
  })

  it('supports variadic args (strict = false)', () => {
    expect(src).toContain('strict = false')
  })

  it('produces JSON Schema-like output', () => {
    expect(src).toContain("type: 'object'")
    expect(src).toContain('properties')
    expect(src).toContain('required')
  })

  it('handles both space and colon command separators', () => {
    expect(src).toContain("replace(/ /g, ':')")
  })

  it('shows available commands on error', () => {
    expect(src).toContain('available_commands')
  })

  it('includes examples in output', () => {
    expect(src).toContain('examples')
  })

  it('documents base_flags separately', () => {
    expect(src).toContain('base_flags')
  })
})

describe('workflows/delete.ts (confirmation + --yes)', () => {
  const src = readFileSync(join(COMMANDS_DIR, 'workflows', 'delete.ts'), 'utf-8')

  it('is hand-written (not auto-generated)', () => {
    expect(src).not.toContain('AUTO-GENERATED')
  })

  it('checks isNonInteractive for --yes / non-TTY', () => {
    expect(src).toContain('isNonInteractive')
  })

  it('uses @clack/prompts for confirmation', () => {
    expect(src).toContain('@clack/prompts')
    expect(src).toContain('confirm')
  })

  it('shows success message after delete', () => {
    expect(src).toContain('printSuccess')
  })
})

describe('base-command.ts (semantic exit codes + --yes)', () => {
  const src = readFileSync(join(CLI_ROOT, 'src', 'base-command.ts'), 'utf-8')

  it('imports exit codes', () => {
    expect(src).toContain('EXIT')
    expect(src).toContain('httpStatusToExitCode')
  })

  it('uses httpStatusToExitCode for API errors', () => {
    expect(src).toContain('httpStatusToExitCode(error.statusCode)')
  })

  it('uses EXIT.USAGE_ERROR for auth errors', () => {
    expect(src).toContain('EXIT.USAGE_ERROR')
  })

  it('uses EXIT.USAGE_ERROR for missing tenant', () => {
    expect(src).toContain('EXIT.USAGE_ERROR')
  })

  it('has --yes flag', () => {
    expect(src).toContain("yes: Flags.boolean")
    expect(src).toContain("char: 'y'")
  })

  it('has isNonInteractive helper', () => {
    expect(src).toContain('isNonInteractive')
    expect(src).toContain('process.stdout.isTTY')
  })
})
