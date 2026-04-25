/**
 * Tests for generated command files.
 *
 * Verifies the generated TypeScript files exist and have correct structure.
 * These tests validate the codegen pipeline: YAML → generate → .ts files.
 */

import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { dirname } from 'node:path'
import { describe, it, expect } from 'vitest'

const CLI_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..')
const COMMANDS_DIR = join(CLI_ROOT, 'src', 'commands')

// Generated commands that should exist (from cli-config.yaml)
const GENERATED_COMMANDS = [
  // Existing
  { topic: 'alerts', command: 'list' },
  { topic: 'alerts', command: 'get' },
  { topic: 'alerts', command: 'search' },
  { topic: 'tasks', command: 'list' },
  { topic: 'tasks', command: 'get' },
  { topic: 'integrations', command: 'list' },
  { topic: 'integrations', command: 'get' },
  { topic: 'integrations', command: 'health' },
  { topic: 'task-runs', command: 'list' },
  { topic: 'task-runs', command: 'get' },
  { topic: 'workflow-runs', command: 'list' },
  { topic: 'workflow-runs', command: 'get' },
  { topic: 'workflow-runs', command: 'status' },
  { topic: 'workflows', command: 'list' },
  { topic: 'workflows', command: 'get' },
  // New generated
  { topic: 'workflows', command: 'update' },
  { topic: 'workflows', command: 'node-templates' },
  { topic: 'integrations', command: 'tools' },
  // Skills
  { topic: 'skills', command: 'list' },
  { topic: 'skills', command: 'get' },
  { topic: 'skills', command: 'delete' },
  // skills/tree is hand-written (see below)
  // Knowledge Units
  { topic: 'knowledge-units', command: 'search' },
  { topic: 'knowledge-units', command: 'list-tables' },
  { topic: 'knowledge-units', command: 'get-table' },
  { topic: 'knowledge-units', command: 'list-documents' },
  { topic: 'knowledge-units', command: 'get-document' },
  { topic: 'knowledge-units', command: 'list-indexes' },
  { topic: 'knowledge-units', command: 'get-index' },
  // Schedules
  { topic: 'schedules', command: 'list' },
  { topic: 'schedules', command: 'create' },
  { topic: 'schedules', command: 'update' },
  { topic: 'schedules', command: 'delete' },
  // Control Event Rules
  { topic: 'control-event-rules', command: 'list' },
  { topic: 'control-event-rules', command: 'get' },
  { topic: 'control-event-rules', command: 'create' },
  { topic: 'control-event-rules', command: 'update' },
  { topic: 'control-event-rules', command: 'delete' },
]

// Hand-written commands that should exist
const HAND_WRITTEN_COMMANDS = [
  { topic: 'tasks', command: 'run' },
  { topic: 'tasks', command: 'create' },
  { topic: 'tasks', command: 'update' },
  { topic: 'tasks', command: 'compile' },
  { topic: 'tasks', command: 'run-adhoc' },
  { topic: 'workflows', command: 'run' },
  { topic: 'workflows', command: 'compose' },
  { topic: 'alerts', command: 'analyze' },
  { topic: 'alerts', command: 'watch' },
  { topic: 'alerts', command: 'validate' },
  { topic: 'integrations', command: 'run-tool' },
  { topic: 'workflow-runs', command: 'watch' },
  { topic: 'workflows', command: 'delete' },
  { topic: 'tools', command: 'list' },
  { topic: 'tools', command: 'get' },
  { topic: 'skills', command: 'tree' },
]

describe('generated command files', () => {
  for (const { topic, command } of GENERATED_COMMANDS) {
    it(`${topic}/${command}.ts exists and has AUTO-GENERATED header`, () => {
      const filePath = join(COMMANDS_DIR, topic, `${command}.ts`)
      expect(existsSync(filePath), `${topic}/${command}.ts should exist`).toBe(true)

      const content = readFileSync(filePath, 'utf-8')
      expect(content).toContain('AUTO-GENERATED')
      expect(content).toContain('BaseCommand')
    })
  }
})

describe('hand-written command files', () => {
  for (const { topic, command } of HAND_WRITTEN_COMMANDS) {
    it(`${topic}/${command}.ts exists and does NOT have AUTO-GENERATED header`, () => {
      const filePath = join(COMMANDS_DIR, topic, `${command}.ts`)
      expect(existsSync(filePath), `${topic}/${command}.ts should exist`).toBe(true)

      const content = readFileSync(filePath, 'utf-8')
      expect(content).not.toContain('AUTO-GENERATED')
    })
  }
})

describe('new generated commands structure', () => {
  it('workflows/update.ts uses PATCH method and data flag', () => {
    const content = readFileSync(join(COMMANDS_DIR, 'workflows', 'update.ts'), 'utf-8')
    expect(content).toContain("'PATCH'")
    expect(content).toContain('parseDataFlag')
  })

  it('workflows/delete.ts uses DELETE method (now hand-written with confirmation)', () => {
    const content = readFileSync(join(COMMANDS_DIR, 'workflows', 'delete.ts'), 'utf-8')
    expect(content).toContain("'DELETE'")
    expect(content).toContain('isNonInteractive') // confirmation gate
  })

  it('workflows/node-templates.ts hits /workflows/node-templates', () => {
    const content = readFileSync(join(COMMANDS_DIR, 'workflows', 'node-templates.ts'), 'utf-8')
    expect(content).toContain('/workflows/node-templates')
  })

  it('integrations/tools.ts hits /integrations/registry/{integration_type}', () => {
    const content = readFileSync(join(COMMANDS_DIR, 'integrations', 'tools.ts'), 'utf-8')
    expect(content).toContain('/integrations/registry/{integration_type}')
  })

  it('tools/list.ts hits /integrations/tools/all and unwraps array', () => {
    const content = readFileSync(join(COMMANDS_DIR, 'tools', 'list.ts'), 'utf-8')
    expect(content).toContain('/integrations/tools/all')
    expect(content).toContain('response.data.tools') // unwraps the array
  })
})
