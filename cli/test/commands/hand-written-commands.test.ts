/**
 * Structural tests for hand-written commands.
 *
 * Verifies that each hand-written command:
 * - Exports a default class extending BaseCommand
 * - Has the expected static properties (description, flags, args)
 * - Imports the correct utilities
 */

import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { dirname } from 'node:path'
import { describe, it, expect } from 'vitest'

const CLI_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..')
const COMMANDS_DIR = join(CLI_ROOT, 'src', 'commands')

function readCmd(topic: string, command: string): string {
  return readFileSync(join(COMMANDS_DIR, topic, `${command}.ts`), 'utf-8')
}

describe('tasks/create.ts', () => {
  const src = readCmd('tasks', 'create')

  it('extends BaseCommand', () => {
    expect(src).toContain('extends BaseCommand')
  })

  it('imports readScriptFlag for @filepath support', () => {
    expect(src).toContain('readScriptFlag')
  })

  it('has required --name and --script flags', () => {
    expect(src).toContain("name: Flags.string")
    expect(src).toContain("script: Flags.string")
    expect(src).toMatch(/name:.*required: true/s)
    expect(src).toMatch(/script:.*required: true/s)
  })

  it('has optional function and scope flags with options', () => {
    expect(src).toContain("function: Flags.string")
    expect(src).toContain("scope: Flags.string")
    expect(src).toContain('options:')
  })

  it('POSTs to /tasks', () => {
    expect(src).toContain("'/tasks'")
    expect(src).toContain("'POST'")
  })
})

describe('tasks/update.ts', () => {
  const src = readCmd('tasks', 'update')

  it('extends BaseCommand', () => {
    expect(src).toContain('extends BaseCommand')
  })

  it('has task_id arg', () => {
    expect(src).toContain('task_id: Args.string')
  })

  it('imports readScriptFlag', () => {
    expect(src).toContain('readScriptFlag')
  })

  it('errors when nothing to update', () => {
    expect(src).toContain('Nothing to update')
  })

  it('PUTs to /tasks/{task_id}', () => {
    expect(src).toContain("'PUT'")
    expect(src).toContain('/tasks/{task_id}')
  })
})

describe('tasks/compile.ts', () => {
  const src = readCmd('tasks', 'compile')

  it('has script as a positional arg', () => {
    expect(src).toContain('script: Args.string')
  })

  it('POSTs to /tasks/analyze', () => {
    expect(src).toContain("'/tasks/analyze'")
    expect(src).toContain("'POST'")
  })

  it('sends script in body', () => {
    expect(src).toContain('{ body: { script } }')
  })

  it('shows compilation success/failure in table mode', () => {
    expect(src).toContain('Compilation successful')
    expect(src).toContain('Compilation failed')
  })

  it('shows tools used', () => {
    expect(src).toContain('tools_used')
  })
})

describe('tasks/run-adhoc.ts', () => {
  const src = readCmd('tasks', 'run-adhoc')

  it('has script as a positional arg', () => {
    expect(src).toContain('script: Args.string')
  })

  it('POSTs to /tasks/run', () => {
    expect(src).toContain("'/tasks/run'")
  })

  it('sends cy_script in body', () => {
    expect(src).toContain('cy_script: script')
  })

  it('supports --no-watch flag', () => {
    expect(src).toContain('allowNo: true')
  })

  it('polls task-runs for completion', () => {
    expect(src).toContain('/task-runs/')
    expect(src).toContain('watchTaskRun')
  })
})

describe('alerts/validate.ts', () => {
  const src = readCmd('alerts', 'validate')

  it('has required --data flag', () => {
    expect(src).toContain("data: Flags.string")
    expect(src).toMatch(/data:.*required: true/s)
  })

  it('uses client-side validateAlert', () => {
    expect(src).toContain('validateAlert')
    expect(src).not.toContain("'/alerts/validate'")
  })

  it('shows validation errors and warnings', () => {
    expect(src).toContain('Errors:')
    expect(src).toContain('Warnings:')
  })
})

describe('workflows/compose.ts', () => {
  const src = readCmd('workflows', 'compose')

  it('has required --data flag', () => {
    expect(src).toContain("data: Flags.string")
    expect(src).toMatch(/data:.*required: true/s)
  })

  it('has optional --execute flag', () => {
    expect(src).toContain("execute: Flags.boolean")
  })

  it('POSTs to /workflows/compose', () => {
    expect(src).toContain("'/workflows/compose'")
    expect(src).toContain("'POST'")
  })

  it('uses result.status (not result.success) for outcome', () => {
    expect(src).toContain("result.status === 'success'")
    expect(src).not.toContain('result.success')
  })

  it('handles needs_decision status', () => {
    expect(src).toContain('needs_decision')
  })
})

describe('integrations/run-tool.ts', () => {
  const src = readCmd('integrations', 'run-tool')

  it('has integration_id and action_id args', () => {
    expect(src).toContain('integration_id: Args.string')
    expect(src).toContain('action_id: Args.string')
  })

  it('has --args flag with @filepath support', () => {
    expect(src).toContain("args: Flags.string")
    expect(src).toContain('parseDataFlag')
  })

  it('has --capture-schema flag', () => {
    expect(src).toContain("'capture-schema': Flags.boolean")
  })

  it('has --timeout flag', () => {
    expect(src).toContain("timeout: Flags.integer")
  })

  it('uses correct route with action_id in path', () => {
    expect(src).toContain('/tools/')
    expect(src).toContain('/execute')
    expect(src).toContain('actId')
  })
})

describe('tools/get.ts', () => {
  const src = readCmd('tools', 'get')

  it('has fqns arg for tool FQNs', () => {
    expect(src).toContain('fqns: Args.string')
  })

  it('allows multiple args (strict = false)', () => {
    expect(src).toContain('strict = false')
  })

  it('GETs /integrations/tools/all', () => {
    expect(src).toContain("'/integrations/tools/all'")
  })

  it('builds a Map from array response for FQN lookup', () => {
    expect(src).toContain('new Map')
    expect(src).toContain('toolsByFqn')
  })
})
