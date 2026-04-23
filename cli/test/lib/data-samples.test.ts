/**
 * Tests for data-samples.ts — listExamples and resolveExample.
 */

import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { listExamples, resolveExample } from '../../src/lib/data-samples.js'
import type { DataSample } from '../../src/lib/data-samples.js'

/** Strip ANSI escape codes so we can assert on plain text content. */
const stripAnsi = (s: string): string => s.replace(/\u001B\[\d+(?:;\d+)*m/g, '')

describe('listExamples', () => {
  let logSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    logSpy = vi.spyOn(console, 'log').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  const baseEntity = (samples: DataSample[] | null) => ({
    name: 'Test Entity',
    data_samples: samples,
  })

  const baseOptions = { entityType: 'task', runCommand: 'analysi tasks run' }

  it('prints "No data samples" message for null samples', () => {
    listExamples(baseEntity(null), 'ent-123', baseOptions)

    const allOutput = logSpy.mock.calls.map((c) => stripAnsi(String(c[0] ?? ''))).join('\n')
    expect(allOutput).toContain('No data samples defined for this task')
  })

  it('prints "No data samples" message for empty array', () => {
    listExamples(baseEntity([]), 'ent-123', baseOptions)

    const allOutput = logSpy.mock.calls.map((c) => stripAnsi(String(c[0] ?? ''))).join('\n')
    expect(allOutput).toContain('No data samples defined for this task')
  })

  it('prints numbered list for samples with names', () => {
    const samples: DataSample[] = [
      { name: 'Sample One', input: { key: 'val' } },
      { name: 'Sample Two', input: { key: 'other' } },
    ]
    listExamples(baseEntity(samples), 'ent-456', baseOptions)

    const allOutput = logSpy.mock.calls.map((c) => stripAnsi(String(c[0] ?? ''))).join('\n')
    expect(allOutput).toContain('#1')
    expect(allOutput).toContain('Sample One')
    expect(allOutput).toContain('#2')
    expect(allOutput).toContain('Sample Two')
  })

  it('truncates long preview to 100 characters', () => {
    const longValue = 'x'.repeat(200)
    const samples: DataSample[] = [{ name: 'Long', input: { big: longValue } }]
    listExamples(baseEntity(samples), 'ent-789', baseOptions)

    const allOutput = logSpy.mock.calls.map((c) => stripAnsi(String(c[0] ?? ''))).join('\n')
    // The source truncates to 97 chars + '...' = 100 visible chars
    expect(allOutput).toContain('...')
    // No single printed segment should exceed 100 chars of JSON preview
    const previewLines = logSpy.mock.calls
      .map((c) => stripAnsi(String(c[0] ?? '')).trim())
      .filter((line) => line.startsWith('{'))
    for (const line of previewLines) {
      expect(line.length).toBeLessThanOrEqual(100)
    }
  })
})

describe('resolveExample', () => {
  const errorFn = vi.fn((msg: string) => {
    throw new Error(msg)
  }) as unknown as (msg: string) => never

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('returns sample.input when present (envelope format)', () => {
    const samples: DataSample[] = [{ name: 'S1', input: { alert_id: '42' } }]
    expect(resolveExample(samples, 1, 'task', errorFn)).toEqual({ alert_id: '42' })
  })

  it('returns raw sample when no input field', () => {
    const samples: DataSample[] = [{ name: 'Raw', description: 'no input field' }]
    const result = resolveExample(samples, 1, 'task', errorFn)
    expect(result).toEqual({ name: 'Raw', description: 'no input field' })
  })

  it('calls errorFn for null samples', () => {
    expect(() => resolveExample(null, 1, 'task', errorFn)).toThrow(
      'This task has no data samples',
    )
  })

  it('calls errorFn for empty samples array', () => {
    expect(() => resolveExample([], 1, 'task', errorFn)).toThrow(
      'This task has no data samples',
    )
  })

  it('calls errorFn for index 0 (below 1-based range)', () => {
    const samples: DataSample[] = [{ input: 'data' }]
    expect(() => resolveExample(samples, 0, 'workflow', errorFn)).toThrow(
      'Example #0 does not exist',
    )
  })

  it('calls errorFn for index exceeding sample count', () => {
    const samples: DataSample[] = [{ input: 'a' }, { input: 'b' }]
    expect(() => resolveExample(samples, 3, 'task', errorFn)).toThrow(
      'Example #3 does not exist',
    )
  })

  it('uses 1-based indexing (exampleNum=1 returns first sample)', () => {
    const samples: DataSample[] = [
      { input: 'first' },
      { input: 'second' },
    ]
    expect(resolveExample(samples, 1, 'task', errorFn)).toBe('first')
    expect(resolveExample(samples, 2, 'task', errorFn)).toBe('second')
  })

  it('returns input even when it is a falsy value (e.g., empty string)', () => {
    const samples: DataSample[] = [{ input: '' }]
    expect(resolveExample(samples, 1, 'task', errorFn)).toBe('')
  })
})
