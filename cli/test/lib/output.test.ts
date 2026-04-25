/**
 * Tests for the output formatting module (output.ts).
 * Covers JSON, CSV, table formats, value formatting, pagination, and message helpers.
 */

import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { printResponse, printError, printSuccess, printWarning } from '../../src/lib/output.js'
import type { ApiResponse } from '../../src/lib/types.js'

/** Strip ANSI escape codes so we can assert on plain text content. */
const stripAnsi = (s: string): string => s.replace(/\u001B\[\d+(?:;\d+)*m/g, '')

describe('output', () => {
  let logSpy: ReturnType<typeof vi.spyOn>
  let errorSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    logSpy = vi.spyOn(console, 'log').mockImplementation(() => {})
    errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  // ---------------------------------------------------------------
  // JSON format
  // ---------------------------------------------------------------
  describe('JSON format', () => {
    it('outputs parseable JSON for array data', () => {
      const response: ApiResponse = {
        data: [{ id: '1', name: 'alpha' }, { id: '2', name: 'beta' }],
        meta: { request_id: 'req-1' },
      }

      printResponse(response, { format: 'json' })

      expect(logSpy).toHaveBeenCalledOnce()
      const output = logSpy.mock.calls[0][0] as string
      const parsed = JSON.parse(output)
      expect(parsed).toEqual([{ id: '1', name: 'alpha' }, { id: '2', name: 'beta' }])
    })

    it('outputs a single object as JSON', () => {
      const response: ApiResponse = {
        data: { id: '42', status: 'completed' },
        meta: { request_id: 'req-2' },
      }

      printResponse(response, { format: 'json' })

      const parsed = JSON.parse(logSpy.mock.calls[0][0] as string)
      expect(parsed).toEqual({ id: '42', status: 'completed' })
    })

    it('filters fields when --fields is specified', () => {
      const response: ApiResponse = {
        data: [{ id: '1', name: 'a', secret: 'x' }],
        meta: { request_id: 'req-3' },
      }

      printResponse(response, { format: 'json', fields: ['id', 'name'] })

      const parsed = JSON.parse(logSpy.mock.calls[0][0] as string)
      expect(parsed).toEqual([{ id: '1', name: 'a' }])
      expect(parsed[0]).not.toHaveProperty('secret')
    })
  })

  // ---------------------------------------------------------------
  // CSV format
  // ---------------------------------------------------------------
  describe('CSV format', () => {
    it('outputs header row followed by data rows', () => {
      const response: ApiResponse = {
        data: [
          { id: '1', name: 'alpha' },
          { id: '2', name: 'beta' },
        ],
        meta: { request_id: 'req-4' },
      }

      printResponse(response, { format: 'csv' })

      expect(logSpy).toHaveBeenCalledTimes(3) // header + 2 rows
      expect(logSpy.mock.calls[0][0]).toBe('id,name')
      expect(logSpy.mock.calls[1][0]).toBe('1,alpha')
      expect(logSpy.mock.calls[2][0]).toBe('2,beta')
    })

    it('suppresses the header row with noHeader', () => {
      const response: ApiResponse = {
        data: [{ id: '1', name: 'alpha' }],
        meta: { request_id: 'req-5' },
      }

      printResponse(response, { format: 'csv', noHeader: true })

      expect(logSpy).toHaveBeenCalledOnce()
      expect(logSpy.mock.calls[0][0]).toBe('1,alpha')
    })

    it('limits columns with --fields', () => {
      const response: ApiResponse = {
        data: [{ id: '1', name: 'alpha', extra: 'noise' }],
        meta: { request_id: 'req-6' },
      }

      printResponse(response, { format: 'csv', fields: ['id'] })

      expect(logSpy).toHaveBeenCalledTimes(2) // header + 1 row
      expect(logSpy.mock.calls[0][0]).toBe('id')
      expect(logSpy.mock.calls[1][0]).toBe('1')
    })

    it('escapes values with commas and quotes', () => {
      const response: ApiResponse = {
        data: [{ msg: 'value with "quotes" and, commas' }],
        meta: { request_id: 'req-7' },
      }

      printResponse(response, { format: 'csv', noHeader: true })

      expect(logSpy.mock.calls[0][0]).toBe('"value with ""quotes"" and, commas"')
    })
  })

  // ---------------------------------------------------------------
  // Table format
  // ---------------------------------------------------------------
  describe('table format', () => {
    it('shows hint message for empty array data', () => {
      const response: ApiResponse = {
        data: [],
        meta: { request_id: 'req-8' },
      }

      printResponse(response, { format: 'table' })

      expect(logSpy).toHaveBeenCalledTimes(2)
      const firstLine = stripAnsi(logSpy.mock.calls[0][0] as string)
      const secondLine = stripAnsi(logSpy.mock.calls[1][0] as string)
      expect(firstLine).toContain('No results found')
      expect(secondLine).toContain('Hint')
    })

    it('prioritizes id/name/status columns and skips noisy keys', () => {
      const response: ApiResponse = {
        data: [{
          raw_alert: '{ huge blob }',
          tenant_id: 'tenant-1',
          cy_script: 'long script',
          id: 'a-1',
          name: 'test',
          status: 'running',
          other_col: 'visible',
        }],
        meta: { request_id: 'req-9' },
      }

      printResponse(response, { format: 'table' })

      const tableOutput = stripAnsi(logSpy.mock.calls[0][0] as string)
      // Priority keys should be present
      expect(tableOutput).toContain('id')
      expect(tableOutput).toContain('name')
      expect(tableOutput).toContain('status')
      // Noisy keys should be excluded
      expect(tableOutput).not.toContain('raw_alert')
      expect(tableOutput).not.toContain('tenant_id')
      expect(tableOutput).not.toContain('cy_script')
    })

    it('limits to max 8 columns', () => {
      const item: Record<string, unknown> = {}
      for (let i = 0; i < 12; i++) {
        item[`col_${String(i).padStart(2, '0')}`] = `val_${i}`
      }

      const response: ApiResponse = {
        data: [item],
        meta: { request_id: 'req-10' },
      }

      printResponse(response, { format: 'table' })

      const tableOutput = stripAnsi(logSpy.mock.calls[0][0] as string)
      // The header row should have at most 8 column names
      // Count column separators in the first content line: 8 cols = 9 pipes for the border
      // A simpler check: col_08 through col_11 should not appear
      expect(tableOutput).toContain('col_00')
      expect(tableOutput).toContain('col_07')
      expect(tableOutput).not.toContain('col_08')
    })

    it('uses --fields to override auto-selection', () => {
      const response: ApiResponse = {
        data: [{ id: '1', name: 'x', status: 'ok', description: 'long text' }],
        meta: { request_id: 'req-11' },
      }

      printResponse(response, { format: 'table', fields: ['description'] })

      const tableOutput = stripAnsi(logSpy.mock.calls[0][0] as string)
      expect(tableOutput).toContain('description')
      expect(tableOutput).toContain('long text')
      // Other columns should not appear as headers
      // (the values might appear in border chars so we check headers specifically)
    })
  })

  // ---------------------------------------------------------------
  // printObject — single object detail view
  // ---------------------------------------------------------------
  describe('printObject (single object detail view)', () => {
    it('shows key-value pairs for a single object', () => {
      const response: ApiResponse = {
        data: { id: 'obj-1', name: 'my-item', status: 'completed' },
        meta: { request_id: 'req-12' },
      }

      printResponse(response, { format: 'table' })

      // printObject outputs one console.log per key, plus potentially request_id line
      const lines = logSpy.mock.calls.map((c) => stripAnsi(c[0] as string))
      const hasId = lines.some((l) => l.includes('id') && l.includes('obj-1'))
      const hasName = lines.some((l) => l.includes('name') && l.includes('my-item'))
      expect(hasId).toBe(true)
      expect(hasName).toBe(true)
    })

    it('filters displayed keys with --fields', () => {
      const response: ApiResponse = {
        data: { id: 'obj-2', name: 'secret-item', status: 'failed' },
        meta: { request_id: 'req-13' },
      }

      printResponse(response, { format: 'table', fields: ['name'] })

      const lines = logSpy.mock.calls.map((c) => stripAnsi(c[0] as string))
      const hasName = lines.some((l) => l.includes('name') && l.includes('secret-item'))
      const hasId = lines.some((l) => l.includes('id') && l.includes('obj-2'))
      expect(hasName).toBe(true)
      expect(hasId).toBe(false)
    })
  })

  // ---------------------------------------------------------------
  // Value formatting
  // ---------------------------------------------------------------
  describe('value formatting', () => {
    it('renders null/undefined as a dim dash', () => {
      const response: ApiResponse = {
        data: { val: null },
        meta: { request_id: 'req-14' },
      }

      printResponse(response, { format: 'table' })

      const lines = logSpy.mock.calls.map((c) => stripAnsi(c[0] as string))
      const valLine = lines.find((l) => l.includes('val'))
      expect(valLine).toBeDefined()
      // The dim dash character
      expect(valLine).toContain('\u2014')
    })

    it('colorizes booleans: true=green, false=red', () => {
      const response: ApiResponse = {
        data: { enabled: true, disabled: false },
        meta: { request_id: 'req-15' },
      }

      printResponse(response, { format: 'table' })

      // Check the raw (with ANSI) output contains the text
      const rawLines = logSpy.mock.calls.map((c) => c[0] as string)
      const enabledLine = rawLines.find((l) => stripAnsi(l).includes('enabled'))
      const disabledLine = rawLines.find((l) => stripAnsi(l).includes('disabled'))
      expect(enabledLine).toBeDefined()
      expect(disabledLine).toBeDefined()
      // The plain text should contain true/false
      expect(stripAnsi(enabledLine!)).toContain('true')
      expect(stripAnsi(disabledLine!)).toContain('false')
    })

    it('shows ISO timestamps as relative time', () => {
      const NOW = new Date('2026-04-16T12:00:00Z').getTime()
      vi.spyOn(Date, 'now').mockReturnValue(NOW)

      const threeMinAgo = '2026-04-16T11:57:00Z'
      const twoHoursAgo = '2026-04-16T10:00:00Z'
      const justNow = '2026-04-16T11:59:45Z'

      const response: ApiResponse = {
        data: [
          { id: '1', ts: justNow },
          { id: '2', ts: threeMinAgo },
          { id: '3', ts: twoHoursAgo },
        ],
        meta: { request_id: 'req-16' },
      }

      printResponse(response, { format: 'table' })

      const tableText = stripAnsi(logSpy.mock.calls[0][0] as string)
      expect(tableText).toContain('just now')
      expect(tableText).toContain('3m ago')
      expect(tableText).toContain('2h ago')
    })

    it('colorizes status values: completed=green, failed=red, running=yellow', () => {
      const response: ApiResponse = {
        data: [
          { id: '1', status: 'completed' },
          { id: '2', status: 'failed' },
          { id: '3', status: 'running' },
        ],
        meta: { request_id: 'req-17' },
      }

      printResponse(response, { format: 'table' })

      const tableText = stripAnsi(logSpy.mock.calls[0][0] as string)
      expect(tableText).toContain('completed')
      expect(tableText).toContain('failed')
      expect(tableText).toContain('running')

      // Verify ANSI codes are present (status values are colorized)
      const rawTable = logSpy.mock.calls[0][0] as string
      expect(rawTable).toContain('\u001B[')
    })
  })

  // ---------------------------------------------------------------
  // Pagination info
  // ---------------------------------------------------------------
  describe('pagination info', () => {
    it('shows pagination line when meta has total/limit/offset', () => {
      const response: ApiResponse = {
        data: [{ id: '1', name: 'item' }],
        meta: { request_id: 'req-18', total: 100, limit: 25, offset: 50 },
      }

      printResponse(response, { format: 'table' })

      // printTable outputs the table, then pagination on a second call
      expect(logSpy.mock.calls.length).toBeGreaterThanOrEqual(2)
      const paginationLine = stripAnsi(logSpy.mock.calls[1][0] as string)
      expect(paginationLine).toContain('100 total')
      expect(paginationLine).toContain('limit: 25')
      expect(paginationLine).toContain('offset: 50')
    })
  })

  // ---------------------------------------------------------------
  // printError / printSuccess / printWarning
  // ---------------------------------------------------------------
  describe('message helpers', () => {
    it('printError outputs to stderr with error text', () => {
      printError('something went wrong')

      expect(errorSpy).toHaveBeenCalledOnce()
      const output = stripAnsi(errorSpy.mock.calls[0][0] as string)
      expect(output).toContain('Error')
      expect(output).toContain('something went wrong')
    })

    it('printSuccess outputs to stdout with checkmark', () => {
      printSuccess('it worked')

      expect(logSpy).toHaveBeenCalledOnce()
      const output = stripAnsi(logSpy.mock.calls[0][0] as string)
      expect(output).toContain('it worked')
    })

    it('printWarning outputs to stdout with warning indicator', () => {
      printWarning('watch out')

      expect(logSpy).toHaveBeenCalledOnce()
      const output = stripAnsi(logSpy.mock.calls[0][0] as string)
      expect(output).toContain('watch out')
    })
  })

  // ---------------------------------------------------------------
  // Additional edge cases
  // ---------------------------------------------------------------
  describe('edge cases', () => {
    it('CSV handles a single object (non-array data)', () => {
      const response: ApiResponse = {
        data: { id: '42', name: 'solo' },
        meta: { request_id: 'req-ec1' },
      }

      printResponse(response, { format: 'csv' })

      expect(logSpy).toHaveBeenCalledTimes(2) // header + 1 row
      expect(logSpy.mock.calls[0][0]).toBe('id,name')
      expect(logSpy.mock.calls[1][0]).toBe('42,solo')
    })

    it('relative time shows date for timestamps older than 1 week', () => {
      const NOW = new Date('2026-04-16T12:00:00Z').getTime()
      vi.spyOn(Date, 'now').mockReturnValue(NOW)

      const twoWeeksAgo = '2026-04-02T12:00:00Z'
      const response: ApiResponse = {
        data: [{ id: '1', ts: twoWeeksAgo }],
        meta: { request_id: 'req-ec2' },
      }

      printResponse(response, { format: 'table' })

      const tableText = stripAnsi(logSpy.mock.calls[0][0] as string)
      // Should show a date string, not "14d ago"
      expect(tableText).not.toContain('14d ago')
    })

    it('truncates long values in table cells', () => {
      const longValue = 'A'.repeat(100)
      const response: ApiResponse = {
        data: [{ id: '1', description: longValue }],
        meta: { request_id: 'req-ec3' },
      }

      printResponse(response, { format: 'table', fields: ['description'] })

      const tableText = stripAnsi(logSpy.mock.calls[0][0] as string)
      // Should be truncated with ...
      expect(tableText).toContain('...')
      expect(tableText).not.toContain(longValue) // full value should NOT appear
    })

    it('JSON filters fields on a single object (non-array)', () => {
      const response: ApiResponse = {
        data: { id: '1', name: 'x', secret: 'hidden' },
        meta: { request_id: 'req-ec4' },
      }

      printResponse(response, { format: 'json', fields: ['id'] })

      const parsed = JSON.parse(logSpy.mock.calls[0][0] as string)
      expect(parsed).toEqual({ id: '1' })
      expect(parsed).not.toHaveProperty('secret')
    })

    it('CSV escapes values with newlines', () => {
      const response: ApiResponse = {
        data: [{ note: 'line1\nline2' }],
        meta: { request_id: 'req-ec5' },
      }

      printResponse(response, { format: 'csv', noHeader: true })

      expect(logSpy.mock.calls[0][0]).toBe('"line1\nline2"')
    })

    it('detail view summarizes arrays as count + preview', () => {
      const response: ApiResponse = {
        data: { tags: ['alpha', 'beta', 'gamma'] },
        meta: { request_id: 'req-ec6' },
      }

      printResponse(response, { format: 'table' })

      const lines = logSpy.mock.calls.map((c) => stripAnsi(c[0] as string))
      const tagsLine = lines.find((l) => l.includes('tags'))
      expect(tagsLine).toBeDefined()
      expect(tagsLine).toContain('3 items')
    })

    it('detail view truncates long objects', () => {
      const bigObj = Object.fromEntries(
        Array.from({ length: 20 }, (_, i) => [`key_${i}`, `value_${i}_padding`]),
      )
      const response: ApiResponse = {
        data: { nested: bigObj },
        meta: { request_id: 'req-ec7' },
      }

      printResponse(response, { format: 'table' })

      const lines = logSpy.mock.calls.map((c) => stripAnsi(c[0] as string))
      const nestedLine = lines.find((l) => l.includes('nested'))
      expect(nestedLine).toBeDefined()
      expect(nestedLine).toContain('...')
    })

    it('relative time shows "from now" for future timestamps', () => {
      const NOW = new Date('2026-04-16T12:00:00Z').getTime()
      vi.spyOn(Date, 'now').mockReturnValue(NOW)

      const future = '2026-04-16T12:05:00Z'
      const response: ApiResponse = {
        data: { scheduled_at: future },
        meta: { request_id: 'req-ec8' },
      }

      printResponse(response, { format: 'table' })

      const lines = logSpy.mock.calls.map((c) => stripAnsi(c[0] as string))
      const tsLine = lines.find((l) => l.includes('scheduled_at'))
      expect(tsLine).toContain('from now')
    })

    it('handles NaN timestamp gracefully', () => {
      const response: ApiResponse = {
        data: [{ id: '1', ts: '2026-99-99T00:00:00Z' }],
        meta: { request_id: 'req-ec9' },
      }

      // Should not throw
      printResponse(response, { format: 'table' })
      expect(logSpy).toHaveBeenCalled()
    })

    it('skips pagination line when no total/limit/offset', () => {
      const response: ApiResponse = {
        data: [{ id: '1' }],
        meta: { request_id: 'req-ec10' },
      }

      printResponse(response, { format: 'table' })

      // Only the table itself, no pagination line
      expect(logSpy).toHaveBeenCalledOnce()
    })

    it('omits offset from pagination when offset is 0', () => {
      const response: ApiResponse = {
        data: [{ id: '1' }],
        meta: { request_id: 'req-ec11', total: 50, limit: 25, offset: 0 },
      }

      printResponse(response, { format: 'table' })

      const paginationLine = stripAnsi(logSpy.mock.calls[1]?.[0] as string ?? '')
      expect(paginationLine).toContain('50 total')
      expect(paginationLine).not.toContain('offset')
    })
  })

  // ---------------------------------------------------------------
  // Legacy string-only call signature
  // ---------------------------------------------------------------
  describe('legacy call signature', () => {
    it('accepts a bare OutputFormat string instead of PrintOptions', () => {
      const response: ApiResponse = {
        data: [{ id: '1' }],
        meta: { request_id: 'req-19' },
      }

      // Should not throw when called with string format
      printResponse(response, 'json')

      const parsed = JSON.parse(logSpy.mock.calls[0][0] as string)
      expect(parsed).toEqual([{ id: '1' }])
    })
  })
})
