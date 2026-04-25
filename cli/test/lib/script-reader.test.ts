/**
 * Tests for script-reader.ts — --script flag parser (inline text and @filepath).
 *
 * Uses real temp files for @filepath tests.
 */

import { describe, expect, it, beforeAll, afterAll } from 'vitest'
import { mkdirSync, writeFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { readScriptFlag } from '../../src/lib/script-reader.js'

const TMP = join(tmpdir(), `analysi-cli-script-test-${Date.now()}`)

beforeAll(() => mkdirSync(TMP, { recursive: true }))
afterAll(() => rmSync(TMP, { recursive: true, force: true }))

describe('readScriptFlag', () => {
  // --- inline scripts ---

  it('returns inline script as-is', () => {
    const script = 'result = query_splunk("index=main")'
    expect(readScriptFlag(script)).toBe(script)
  })

  it('trims whitespace from inline script', () => {
    expect(readScriptFlag('  result = 1  ')).toBe('result = 1')
  })

  it('returns raw text without JSON-parsing', () => {
    // A script containing braces should NOT be JSON-parsed
    const script = '{ "not": "parsed" }'
    expect(readScriptFlag(script)).toBe(script)
  })

  // --- @filepath ---

  it('reads file content from @filepath', () => {
    const filePath = join(TMP, 'enrich.cy')
    writeFileSync(filePath, 'result = lookup_ip("1.2.3.4")')

    expect(readScriptFlag(`@${filePath}`)).toBe('result = lookup_ip("1.2.3.4")')
  })

  it('throws "Missing file path" for bare @', () => {
    expect(() => readScriptFlag('@')).toThrow('Missing file path after @')
  })

  it('throws "File not found" for @nonexistent.cy', () => {
    expect(() => readScriptFlag(`@${join(TMP, 'missing.cy')}`)).toThrow('File not found')
  })

  it('preserves newlines in multi-line scripts from file', () => {
    const filePath = join(TMP, 'multiline.cy')
    const content = 'line_one = 1\nline_two = 2\nline_three = 3\n'
    writeFileSync(filePath, content)

    expect(readScriptFlag(`@${filePath}`)).toBe(content)
  })
})
