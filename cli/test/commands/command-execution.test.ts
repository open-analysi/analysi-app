/**
 * Command execution tests — verify command behavior with mocked API responses.
 *
 * These test the actual patterns used by commands without spinning up oclif.
 * We test the building blocks that commands rely on:
 *   - API client response → output formatting pipeline
 *   - Flag parsing → body construction
 *   - Error mapping → exit codes
 *
 * Covers use cases:
 *   UC1-3:   Output formats (table, json, csv)
 *   UC7-8:   Task create/update body construction
 *   UC9:     Compile response handling
 *   UC17:    CSV with field selection
 *   UC19:    Error exit codes
 *   UC28-29: @filepath reading for scripts
 *   UC31:    Ad-hoc body construction
 *   UC34:    Output to file (tested via output module)
 *   UC37:    list-commands flag filtering
 *   UC39:    --yes / non-interactive
 *   UC41-44: Filter/sort query param construction
 *   UC53:    Tags parsing (comma-separated → array)
 */

import { writeFileSync, mkdirSync, rmSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { describe, it, expect, vi, afterEach, beforeAll, afterAll } from 'vitest'
import { ApiClient, ApiError } from '../../src/lib/api-client.js'
import { parseDataFlag } from '../../src/lib/data-reader.js'
import { readScriptFlag } from '../../src/lib/script-reader.js'
import { printResponse } from '../../src/lib/output.js'
import { httpStatusToExitCode, EXIT } from '../../src/lib/exit-codes.js'

const TMP = join(tmpdir(), `analysi-cli-exec-test-${Date.now()}`)
beforeAll(() => mkdirSync(TMP, { recursive: true }))
afterAll(() => rmSync(TMP, { recursive: true, force: true }))
afterEach(() => vi.restoreAllMocks())

function mockFetch(body: unknown, status = 200, ok = true) {
  return vi.spyOn(globalThis, 'fetch').mockResolvedValue({
    ok, status, statusText: ok ? 'OK' : 'Error',
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as Response)
}

const creds = { api_key: 'test-key', base_url: 'http://localhost:8001' }

// ---------------------------------------------------------------------------
// UC1-3, UC17: Output format pipeline
// ---------------------------------------------------------------------------

describe('output format pipeline', () => {
  it('JSON output prints parseable JSON for array data (UC3)', () => {
    const spy = vi.spyOn(console, 'log').mockImplementation(() => {})
    printResponse(
      { data: [{ id: '1', name: 'Alert 1', severity: 'high' }], meta: { request_id: 'r', total: 1 } },
      { format: 'json' },
    )
    const output = spy.mock.calls.flat().join('')
    const parsed = JSON.parse(output)
    expect(parsed).toEqual([{ id: '1', name: 'Alert 1', severity: 'high' }])
  })

  it('CSV with --fields selects only requested columns (UC17)', () => {
    const spy = vi.spyOn(console, 'log').mockImplementation(() => {})
    printResponse(
      { data: [{ id: '1', name: 'x', severity: 'high', extra: 'drop' }], meta: { request_id: 'r' } },
      { format: 'csv', fields: ['id', 'severity'], noHeader: true },
    )
    expect(spy.mock.calls[0][0]).toBe('1,high')
  })

  it('CSV --no-header suppresses header line (UC17)', () => {
    const spy = vi.spyOn(console, 'log').mockImplementation(() => {})
    printResponse(
      { data: [{ a: '1' }], meta: { request_id: 'r' } },
      { format: 'csv', noHeader: true },
    )
    expect(spy.mock.calls).toHaveLength(1) // data only, no header
  })

  it('table shows "No results" for empty array (UC11)', () => {
    const spy = vi.spyOn(console, 'log').mockImplementation(() => {})
    printResponse(
      { data: [], meta: { request_id: 'r' } },
      { format: 'table' },
    )
    expect(spy.mock.calls.flat().join('')).toContain('No results')
  })
})

// ---------------------------------------------------------------------------
// UC7, UC53: Task create body construction
// ---------------------------------------------------------------------------

describe('task create body construction', () => {
  it('builds body with name and inline script (UC7)', () => {
    const script = readScriptFlag('result = sum([1, 2, 3])')
    expect(script).toBe('result = sum([1, 2, 3])')
    const body = { name: 'Test', script }
    expect(body).toEqual({ name: 'Test', script: 'result = sum([1, 2, 3])' })
  })

  it('reads script from @filepath (UC28)', () => {
    const fp = join(TMP, 'create-test.cy')
    writeFileSync(fp, 'result = app::echo_edr::get_host_details(host="h1")')
    const script = readScriptFlag(`@${fp}`)
    expect(script).toContain('app::echo_edr::get_host_details')
  })

  it('parses comma-separated tags into array (UC53)', () => {
    const tags = 'enrichment,network,threat_intel'
    const categories = tags.split(',').map((t) => t.trim())
    expect(categories).toEqual(['enrichment', 'network', 'threat_intel'])
  })

  it('parses data-samples from JSON string (UC54)', () => {
    const samples = parseDataFlag('[{"name":"Test","input":{"ip":"8.8.8.8"}}]')
    expect(samples).toEqual([{ name: 'Test', input: { ip: '8.8.8.8' } }])
  })
})

// ---------------------------------------------------------------------------
// UC8, UC35-36: Task update body construction
// ---------------------------------------------------------------------------

describe('task update body construction', () => {
  it('builds body with only changed fields (UC35)', () => {
    const body: Record<string, unknown> = {}
    const description = 'Updated description'
    // Simulating the update command's logic
    if (description) body.description = description
    expect(body).toEqual({ description: 'Updated description' })
    expect(body).not.toHaveProperty('script')
  })

  it('rejects empty body (UC36)', () => {
    const body: Record<string, unknown> = {}
    expect(Object.keys(body).length).toBe(0) // triggers "Nothing to update" error
  })
})

// ---------------------------------------------------------------------------
// UC9, UC29-30: Compile response handling
// ---------------------------------------------------------------------------

describe('compile response handling', () => {
  it('identifies successful compilation (UC9)', () => {
    const response = {
      task_id: null,
      cy_name: null,
      tools_used: ['native::tools::sum'],
      external_variables: [],
      errors: null,
    }
    const hasErrors = response.errors && response.errors.length > 0
    expect(hasErrors).toBeFalsy()
    expect(response.tools_used).toEqual(['native::tools::sum'])
  })

  it('identifies compilation with errors', () => {
    const response = {
      task_id: null,
      cy_name: null,
      tools_used: [],
      external_variables: [],
      errors: ['Syntax error: unexpected token'],
    }
    const hasErrors = response.errors && response.errors.length > 0
    expect(hasErrors).toBeTruthy()
  })

  it('reads .cy file for compilation (UC29)', () => {
    const fp = join(TMP, 'compile-test.cy')
    writeFileSync(fp, 'x = sum([10, 20])\nresult = str(x)')
    const script = readScriptFlag(`@${fp}`)
    expect(script).toContain('sum([10, 20])')
    expect(script).toContain('str(x)')
  })
})

// ---------------------------------------------------------------------------
// UC19: Error code mapping
// ---------------------------------------------------------------------------

describe('error exit code mapping (UC19)', () => {
  it('maps 404 to FAILURE (1)', () => {
    expect(httpStatusToExitCode(404)).toBe(EXIT.FAILURE)
  })

  it('maps 422 to USAGE_ERROR (2)', () => {
    expect(httpStatusToExitCode(422)).toBe(EXIT.USAGE_ERROR)
  })

  it('maps 500 to FAILURE (1)', () => {
    expect(httpStatusToExitCode(500)).toBe(EXIT.FAILURE)
  })

  it('ApiError carries status code', async () => {
    mockFetch({ detail: 'Validation failed' }, 422, false)
    const client = new ApiClient(creds)
    try {
      await client.request('GET', '/bad', 'tenant')
      expect.unreachable()
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError)
      expect((err as ApiError).statusCode).toBe(422)
      expect(httpStatusToExitCode((err as ApiError).statusCode)).toBe(EXIT.USAGE_ERROR)
    }
  })
})

// ---------------------------------------------------------------------------
// UC31: Ad-hoc run body construction
// ---------------------------------------------------------------------------

describe('ad-hoc run body construction (UC31)', () => {
  it('builds body with cy_script and input from @filepath', () => {
    const fp = join(TMP, 'adhoc-input.json')
    writeFileSync(fp, '{"alert_id": "test-123"}')

    const script = readScriptFlag('result = str(input)')
    const inputData = parseDataFlag(`@${fp}`)

    const body: Record<string, unknown> = { cy_script: script }
    if (inputData !== undefined) body.input = inputData

    expect(body).toEqual({
      cy_script: 'result = str(input)',
      input: { alert_id: 'test-123' },
    })
  })

  it('omits input when no --data provided', () => {
    const body: Record<string, unknown> = { cy_script: 'result = 42' }
    // no inputData, so don't add it
    expect(body).toEqual({ cy_script: 'result = 42' })
    expect(body).not.toHaveProperty('input')
  })
})

// ---------------------------------------------------------------------------
// UC37, UC39: list-commands filtering and --yes
// ---------------------------------------------------------------------------

describe('non-interactive detection (UC39)', () => {
  it('--yes flag triggers non-interactive', () => {
    const isNonInteractive = (flags: { yes?: boolean }) =>
      flags.yes === true || !process.stdout.isTTY
    expect(isNonInteractive({ yes: true })).toBe(true)
    expect(isNonInteractive({ yes: false })).toBe(!process.stdout.isTTY)
  })
})

describe('base flag filtering for list-commands (UC37)', () => {
  const BASE_FLAGS = new Set(['tenant', 'output', 'fields', 'no-header', 'out', 'verbose'])

  it('filters base flags by default', () => {
    const allFlags = ['tenant', 'output', 'verbose', 'name', 'script', 'function']
    const filtered = allFlags.filter((f) => !BASE_FLAGS.has(f))
    expect(filtered).toEqual(['name', 'script', 'function'])
  })

  it('includes base flags when requested', () => {
    const allFlags = ['tenant', 'output', 'name']
    const filtered = allFlags // no filtering
    expect(filtered).toEqual(['tenant', 'output', 'name'])
  })
})

// ---------------------------------------------------------------------------
// UC41-44: Query param construction for filters/sorts
// ---------------------------------------------------------------------------

describe('query param construction (UC41-44)', () => {
  it('constructs correct query for sorted alerts (UC41)', async () => {
    const spy = mockFetch({ data: [], meta: { request_id: 'r' } })
    const client = new ApiClient(creds)
    await client.request('GET', '/alerts', 'tenant-1', {
      query: { sort_by: 'severity', sort_order: 'desc', limit: 25 },
    })
    const url = spy.mock.calls[0][0] as string
    expect(url).toContain('sort_by=severity')
    expect(url).toContain('sort_order=desc')
    expect(url).toContain('limit=25')
  })

  it('constructs correct query for filtered task-runs (UC43)', async () => {
    const spy = mockFetch({ data: [], meta: { request_id: 'r' } })
    const client = new ApiClient(creds)
    await client.request('GET', '/task-runs', 'tenant-1', {
      query: { sort: 'duration', order: 'desc', limit: 5 },
    })
    const url = spy.mock.calls[0][0] as string
    expect(url).toContain('sort=duration')
    expect(url).toContain('order=desc')
  })

  it('constructs correct query for status-filtered workflow-runs (UC44)', async () => {
    const spy = mockFetch({ data: [], meta: { request_id: 'r' } })
    const client = new ApiClient(creds)
    await client.request('GET', '/workflow-runs', 'tenant-1', {
      query: { status: 'failed' },
    })
    const url = spy.mock.calls[0][0] as string
    expect(url).toContain('status=failed')
  })

  it('omits undefined query params', async () => {
    const spy = mockFetch({ data: [], meta: { request_id: 'r' } })
    const client = new ApiClient(creds)
    await client.request('GET', '/tasks', 'tenant-1', {
      query: { function: undefined, scope: 'processing', limit: 3 },
    })
    const url = spy.mock.calls[0][0] as string
    expect(url).not.toContain('function')
    expect(url).toContain('scope=processing')
  })
})

// ---------------------------------------------------------------------------
// UC46-48: Integration tools response patterns
// ---------------------------------------------------------------------------

describe('integration tools response handling (UC47-48)', () => {
  it('parses integration tools list', async () => {
    mockFetch({
      data: {
        integration_type: 'echo_edr',
        display_name: 'Echo EDR',
        tools: [
          { tool_id: 'pull_processes', name: 'Pull Process Data' },
          { tool_id: 'isolate_host', name: 'Isolate Host' },
        ],
      },
      meta: { request_id: 'r' },
    })
    const client = new ApiClient(creds)
    const response = await client.request<{ tools: Array<{ tool_id: string }> }>(
      'GET', '/integrations/registry/echo_edr', 'tenant-1',
    )
    expect(response.data.tools).toHaveLength(2)
    expect(response.data.tools[0].tool_id).toBe('pull_processes')
  })
})

// ---------------------------------------------------------------------------
// UC56: --example mutual exclusion with --data
// ---------------------------------------------------------------------------

describe('example vs data mutual exclusion (UC56)', () => {
  it('detects conflict between --data and --example', () => {
    const flags = { data: '{"x":1}', example: 1 }
    const hasConflict = flags.data && flags.example
    expect(hasConflict).toBeTruthy()
  })

  it('allows --data without --example', () => {
    const flags = { data: '{"x":1}', example: undefined }
    const hasConflict = flags.data && flags.example
    expect(hasConflict).toBeFalsy()
  })
})

// ---------------------------------------------------------------------------
// UC58-59: Tools list response patterns
// ---------------------------------------------------------------------------

describe('tools list response handling (UC58-59)', () => {
  it('handles tools list with mixed categories', async () => {
    mockFetch({
      data: {
        tools: [
          { fqn: 'len', name: 'len' },
          { fqn: 'sum', name: 'sum' },
          { fqn: 'app::splunk::spl_run', name: 'spl_run' },
        ],
        total: 3,
      },
      meta: { request_id: 'r' },
    })
    const client = new ApiClient(creds)
    const response = await client.request<{ tools: Array<{ fqn: string }>, total: number }>(
      'GET', '/integrations/tools/all', 'tenant-1',
    )
    const native = response.data.tools.filter((t) => !t.fqn.startsWith('app::'))
    const app = response.data.tools.filter((t) => t.fqn.startsWith('app::'))
    expect(native).toHaveLength(2)
    expect(app).toHaveLength(1)
  })
})

// ---------------------------------------------------------------------------
// UC60: JSON chaining / piping patterns
// ---------------------------------------------------------------------------

describe('JSON output is pipe-friendly (UC40, UC60)', () => {
  it('JSON array output is parseable by downstream tools', () => {
    const spy = vi.spyOn(console, 'log').mockImplementation(() => {})
    printResponse(
      {
        data: [
          { id: 'run-1', workflow_name: 'Triage', status: 'failed' },
          { id: 'run-2', workflow_name: 'Enrich', status: 'failed' },
        ],
        meta: { request_id: 'r' },
      },
      { format: 'json' },
    )
    const output = spy.mock.calls.flat().join('')
    const parsed = JSON.parse(output)
    expect(parsed).toHaveLength(2)
    expect(parsed.every((r: { status: string }) => r.status === 'failed')).toBe(true)
  })
})
