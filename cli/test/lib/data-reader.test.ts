/**
 * Tests for data-reader.ts — --data flag parser (inline JSON and @filepath).
 *
 * Uses real temp files for @filepath tests.
 */

import { describe, expect, it, beforeAll, afterAll } from 'vitest'
import { mkdirSync, writeFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { parseDataFlag } from '../../src/lib/data-reader.js'

const TMP = join(tmpdir(), `analysi-cli-data-test-${Date.now()}`)

beforeAll(() => mkdirSync(TMP, { recursive: true }))
afterAll(() => rmSync(TMP, { recursive: true, force: true }))

describe('parseDataFlag', () => {
  // --- inline JSON ---

  it('parses inline JSON object', () => {
    const result = parseDataFlag('{"key": "value", "num": 42}')
    expect(result).toEqual({ key: 'value', num: 42 })
  })

  it('parses inline JSON array', () => {
    const result = parseDataFlag('[1, 2, 3]')
    expect(result).toEqual([1, 2, 3])
  })

  it('trims whitespace from value', () => {
    const result = parseDataFlag('  {"a": 1}  ')
    expect(result).toEqual({ a: 1 })
  })

  it('handles nested JSON objects', () => {
    const nested = { outer: { inner: { deep: [1, 2] } } }
    const result = parseDataFlag(JSON.stringify(nested))
    expect(result).toEqual(nested)
  })

  it('throws "Invalid JSON" for inline non-JSON string', () => {
    expect(() => parseDataFlag('not json at all')).toThrow('Invalid JSON')
  })

  it('shows hint about @file.json in inline JSON error message', () => {
    expect(() => parseDataFlag('bad')).toThrow('Hint: use --data @file.json')
  })

  // --- @filepath ---

  it('reads JSON from @filepath', () => {
    const filePath = join(TMP, 'input.json')
    writeFileSync(filePath, '{"loaded": true}')

    const result = parseDataFlag(`@${filePath}`)
    expect(result).toEqual({ loaded: true })
  })

  it('throws "Missing file path" for bare @', () => {
    expect(() => parseDataFlag('@')).toThrow('Missing file path after @')
  })

  it('throws "File not found" for @nonexistent.json', () => {
    expect(() => parseDataFlag(`@${join(TMP, 'no-such-file.json')}`)).toThrow('File not found')
  })

  it('throws "Invalid JSON" for @filepath with corrupt content', () => {
    const filePath = join(TMP, 'corrupt.json')
    writeFileSync(filePath, '{bad json!!!}')

    expect(() => parseDataFlag(`@${filePath}`)).toThrow('Invalid JSON')
  })
})
