/**
 * Unit tests for workflow-progress.ts — WorkflowProgressWatcher.
 *
 * Covers: getStatus, getDetail, watch loop (running transition, completed nodes,
 * failed nodes, terminal states), nodeDuration (via watch output), and edge cases.
 *
 * Mocks globalThis.fetch to simulate API responses and mocks sleep to avoid real delays.
 */

import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { ApiClient } from '../../src/lib/api-client.js'
import { WorkflowProgressWatcher } from '../../src/lib/workflow-progress.js'

// Mock sleep to resolve instantly — avoids 2s polling delays in tests
vi.mock('../../src/lib/cli-utils.js', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../src/lib/cli-utils.js')>()
  return { ...actual, sleep: vi.fn().mockResolvedValue(undefined) }
})

const creds = { api_key: 'test-key', base_url: 'http://localhost:8001' }
const tenantId = 'test-tenant'
const workflowRunId = 'wfr-001'

/** Helper: build a Sifnos-envelope response */
function envelope<T>(data: T, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? 'OK' : 'Error',
    json: async () => ({ data, meta: { request_id: 'r1' } }),
    text: async () => JSON.stringify({ data, meta: { request_id: 'r1' } }),
  } as Response
}

interface StatusPayload {
  workflow_run_id: string
  status: string
  started_at: string | null
  completed_at: string | null
  updated_at: string
}

interface GraphPayload {
  workflow_run_id: string
  is_complete: boolean
  status: string | null
  summary: Record<string, number>
  nodes: Array<{
    node_instance_id: string
    node_id: string
    status: string
    started_at: string | null
    completed_at: string | null
    error_message: string | null
  }>
}

function makeStatus(overrides: Partial<StatusPayload> = {}): StatusPayload {
  return {
    workflow_run_id: workflowRunId,
    status: 'running',
    started_at: '2026-01-01T00:00:00Z',
    completed_at: null,
    updated_at: '2026-01-01T00:00:05Z',
    ...overrides,
  }
}

function makeGraph(overrides: Partial<GraphPayload> = {}): GraphPayload {
  return {
    workflow_run_id: workflowRunId,
    is_complete: false,
    status: 'running',
    summary: {},
    nodes: [],
    ...overrides,
  }
}

describe('WorkflowProgressWatcher', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  // ── getStatus / getDetail ─────────────────────────────────────────

  describe('getStatus', () => {
    it('returns parsed status object', async () => {
      const statusData = makeStatus({ status: 'running' })
      vi.spyOn(globalThis, 'fetch').mockResolvedValue(envelope(statusData))

      const client = new ApiClient(creds)
      const watcher = new WorkflowProgressWatcher(client, tenantId)

      const result = await watcher.getStatus(workflowRunId)
      expect(result).not.toBeNull()
      expect(result!.workflow_run_id).toBe(workflowRunId)
      expect(result!.status).toBe('running')
    })
  })

  describe('getDetail', () => {
    it('returns null when API fails', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValue({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
        json: async () => ({ detail: 'Server error' }),
        text: async () => JSON.stringify({ detail: 'Server error' }),
      } as Response)

      const client = new ApiClient(creds)
      const watcher = new WorkflowProgressWatcher(client, tenantId)

      const result = await watcher.getDetail(workflowRunId)
      expect(result).toBeNull()
    })
  })

  // ── watch() ───────────────────────────────────────────────────────

  describe('watch()', () => {
    beforeEach(() => {
      vi.spyOn(console, 'log').mockImplementation(() => {})
      vi.spyOn(console, 'error').mockImplementation(() => {})
    })

    it('shows "Executing nodes" when status becomes running', async () => {
      let callCount = 0
      vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => {
        callCount++
        const urlStr = String(url)

        if (urlStr.includes('/status')) {
          if (callCount <= 2) {
            return envelope(makeStatus({ status: 'running' }))
          }
          return envelope(makeStatus({ status: 'completed', completed_at: '2026-01-01T00:01:00Z' }))
        }
        if (urlStr.includes('/graph')) {
          return envelope(makeGraph({ nodes: [] }))
        }
        return envelope(null)
      })

      const client = new ApiClient(creds)
      const watcher = new WorkflowProgressWatcher(client, tenantId)

      await watcher.watch(workflowRunId)

      const logs = (console.log as ReturnType<typeof vi.fn>).mock.calls
        .map((args: unknown[]) => args.join(' '))
        .join('\n')

      expect(logs).toContain('Executing nodes')
    })

    it('shows completed nodes from graph (green checkmark + node_id + duration)', async () => {
      let callCount = 0
      vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => {
        callCount++
        const urlStr = String(url)

        if (urlStr.includes('/status')) {
          if (callCount <= 2) {
            return envelope(makeStatus({ status: 'running' }))
          }
          return envelope(makeStatus({ status: 'completed', completed_at: '2026-01-01T00:01:00Z' }))
        }
        if (urlStr.includes('/graph')) {
          return envelope(makeGraph({
            nodes: [
              {
                node_instance_id: 'ni-1',
                node_id: 'enrich_ioc',
                status: 'completed',
                started_at: '2026-01-01T00:00:00Z',
                completed_at: '2026-01-01T00:00:03Z',
                error_message: null,
              },
            ],
          }))
        }
        return envelope(null)
      })

      const client = new ApiClient(creds)
      const watcher = new WorkflowProgressWatcher(client, tenantId)

      await watcher.watch(workflowRunId)

      const logs = (console.log as ReturnType<typeof vi.fn>).mock.calls
        .map((args: unknown[]) => args.join(' '))
        .join('\n')

      expect(logs).toContain('enrich_ioc')
      expect(logs).toContain('3.0s')
    })

    it('shows failed nodes from graph (red X + node_id + error hint)', async () => {
      let callCount = 0
      vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => {
        callCount++
        const urlStr = String(url)

        if (urlStr.includes('/status')) {
          if (callCount <= 2) {
            return envelope(makeStatus({ status: 'running' }))
          }
          return envelope(makeStatus({ status: 'failed' }))
        }
        if (urlStr.includes('/graph')) {
          return envelope(makeGraph({
            nodes: [
              {
                node_instance_id: 'ni-2',
                node_id: 'query_siem',
                status: 'failed',
                started_at: '2026-01-01T00:00:00Z',
                completed_at: '2026-01-01T00:00:01Z',
                error_message: 'Connection refused to Splunk host',
              },
            ],
          }))
        }
        // getDetail call for showFailure
        if (urlStr.includes(`/workflow-runs/${workflowRunId}`) && !urlStr.includes('/status') && !urlStr.includes('/graph')) {
          return envelope({
            workflow_run_id: workflowRunId,
            workflow_name: 'test-wf',
            status: 'failed',
            started_at: '2026-01-01T00:00:00Z',
            completed_at: null,
            error_message: 'Node query_siem failed',
          })
        }
        return envelope(null)
      })

      const client = new ApiClient(creds)
      const watcher = new WorkflowProgressWatcher(client, tenantId)

      await watcher.watch(workflowRunId)

      const logs = (console.log as ReturnType<typeof vi.fn>).mock.calls
        .map((args: unknown[]) => args.join(' '))
        .join('\n')

      expect(logs).toContain('query_siem')
      expect(logs).toContain('Connection refused')
    })

    it('shows "Workflow complete" on terminal completed status', async () => {
      vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => {
        const urlStr = String(url)

        if (urlStr.includes('/status')) {
          return envelope(makeStatus({ status: 'completed', completed_at: '2026-01-01T00:01:00Z' }))
        }
        if (urlStr.includes('/graph')) {
          return envelope(makeGraph({ is_complete: true, nodes: [] }))
        }
        return envelope(null)
      })

      const client = new ApiClient(creds)
      const watcher = new WorkflowProgressWatcher(client, tenantId)

      await watcher.watch(workflowRunId)

      const logs = (console.log as ReturnType<typeof vi.fn>).mock.calls
        .map((args: unknown[]) => args.join(' '))
        .join('\n')

      expect(logs).toContain('Workflow complete')
    })

    it('shows "Workflow failed" with error message on terminal failed status', async () => {
      vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => {
        const urlStr = String(url)

        if (urlStr.includes('/status')) {
          return envelope(makeStatus({ status: 'failed' }))
        }
        if (urlStr.includes('/graph')) {
          return envelope(makeGraph({ nodes: [] }))
        }
        // getDetail for showFailure
        if (urlStr.includes(`/workflow-runs/${workflowRunId}`) && !urlStr.includes('/status') && !urlStr.includes('/graph')) {
          return envelope({
            workflow_run_id: workflowRunId,
            workflow_name: 'test-wf',
            status: 'failed',
            started_at: '2026-01-01T00:00:00Z',
            completed_at: null,
            error_message: 'Maximum retries exceeded for node enrich_ioc',
          })
        }
        return envelope(null)
      })

      const client = new ApiClient(creds)
      const watcher = new WorkflowProgressWatcher(client, tenantId)

      await watcher.watch(workflowRunId)

      const logs = (console.log as ReturnType<typeof vi.fn>).mock.calls
        .map((args: unknown[]) => args.join(' '))
        .join('\n')

      expect(logs).toContain('Workflow failed')
      expect(logs).toContain('Maximum retries exceeded')
    })

    it('shows "Workflow cancelled" on terminal cancelled status', async () => {
      vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => {
        const urlStr = String(url)

        if (urlStr.includes('/status')) {
          return envelope(makeStatus({ status: 'cancelled' }))
        }
        if (urlStr.includes('/graph')) {
          return envelope(makeGraph({
            nodes: [
              {
                node_instance_id: 'ni-c1',
                node_id: 'cancelled_node',
                status: 'cancelled',
                started_at: null,
                completed_at: null,
                error_message: null,
              },
            ],
          }))
        }
        return envelope(null)
      })

      const client = new ApiClient(creds)
      const watcher = new WorkflowProgressWatcher(client, tenantId)

      await watcher.watch(workflowRunId)

      const logs = (console.log as ReturnType<typeof vi.fn>).mock.calls
        .map((args: unknown[]) => args.join(' '))
        .join('\n')

      expect(logs).toContain('cancelled')
    })

    it('shows timeout message when poll exceeds TIMEOUT_MS', async () => {
      let mockTime = 1000000
      vi.spyOn(Date, 'now').mockImplementation(() => {
        const current = mockTime
        mockTime += 11 * 60 * 1000 // jump 11 minutes per call
        return current
      })

      vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => {
        const urlStr = String(url)
        if (urlStr.includes('/status')) {
          return envelope(makeStatus({ status: 'running' }))
        }
        if (urlStr.includes('/graph')) {
          return envelope(makeGraph({ nodes: [] }))
        }
        return envelope(null)
      })

      const client = new ApiClient(creds)
      const watcher = new WorkflowProgressWatcher(client, tenantId)

      await watcher.watch(workflowRunId)

      const logs = (console.log as ReturnType<typeof vi.fn>).mock.calls
        .map((args: unknown[]) => args.join(' '))
        .join('\n')

      expect(logs).toContain('Timed out')
      expect(logs).toContain('Workflow may still be running')
    })
  })

  // ── nodeDuration (tested via watch output) ────────────────────────

  describe('nodeDuration (via watch output)', () => {
    beforeEach(() => {
      vi.spyOn(console, 'log').mockImplementation(() => {})
      vi.spyOn(console, 'error').mockImplementation(() => {})
    })

    it('shows duration in ms for short durations (<1s)', async () => {
      vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => {
        const urlStr = String(url)

        if (urlStr.includes('/status')) {
          return envelope(makeStatus({ status: 'completed', completed_at: '2026-01-01T00:01:00Z' }))
        }
        if (urlStr.includes('/graph')) {
          return envelope(makeGraph({
            nodes: [
              {
                node_instance_id: 'ni-fast',
                node_id: 'fast_lookup',
                status: 'completed',
                started_at: '2026-01-01T00:00:00.000Z',
                completed_at: '2026-01-01T00:00:00.450Z',
                error_message: null,
              },
            ],
          }))
        }
        return envelope(null)
      })

      const client = new ApiClient(creds)
      const watcher = new WorkflowProgressWatcher(client, tenantId)

      await watcher.watch(workflowRunId)

      const logs = (console.log as ReturnType<typeof vi.fn>).mock.calls
        .map((args: unknown[]) => args.join(' '))
        .join('\n')

      expect(logs).toContain('fast_lookup')
      expect(logs).toContain('450ms')
    })

    it('shows duration in seconds for longer durations', async () => {
      vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => {
        const urlStr = String(url)

        if (urlStr.includes('/status')) {
          return envelope(makeStatus({ status: 'completed', completed_at: '2026-01-01T00:01:00Z' }))
        }
        if (urlStr.includes('/graph')) {
          return envelope(makeGraph({
            nodes: [
              {
                node_instance_id: 'ni-slow',
                node_id: 'deep_scan',
                status: 'completed',
                started_at: '2026-01-01T00:00:00Z',
                completed_at: '2026-01-01T00:00:12Z',
                error_message: null,
              },
            ],
          }))
        }
        return envelope(null)
      })

      const client = new ApiClient(creds)
      const watcher = new WorkflowProgressWatcher(client, tenantId)

      await watcher.watch(workflowRunId)

      const logs = (console.log as ReturnType<typeof vi.fn>).mock.calls
        .map((args: unknown[]) => args.join(' '))
        .join('\n')

      expect(logs).toContain('deep_scan')
      expect(logs).toContain('12.0s')
    })
  })

  // ── Edge cases ────────────────────────────────────────────────────

  describe('edge cases', () => {
    beforeEach(() => {
      vi.spyOn(console, 'log').mockImplementation(() => {})
      vi.spyOn(console, 'error').mockImplementation(() => {})
    })

    it('handles null graph response gracefully (continues polling)', async () => {
      let callCount = 0
      vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => {
        callCount++
        const urlStr = String(url)

        if (urlStr.includes('/status')) {
          if (callCount <= 3) {
            return envelope(makeStatus({ status: 'running' }))
          }
          return envelope(makeStatus({ status: 'completed', completed_at: '2026-01-01T00:01:00Z' }))
        }
        if (urlStr.includes('/graph')) {
          // First graph call fails (returns error status), subsequent ones succeed
          if (callCount <= 3) {
            return {
              ok: false,
              status: 500,
              statusText: 'Internal Server Error',
              json: async () => ({ detail: 'Transient error' }),
              text: async () => JSON.stringify({ detail: 'Transient error' }),
            } as Response
          }
          return envelope(makeGraph({ nodes: [] }))
        }
        return envelope(null)
      })

      const client = new ApiClient(creds)
      const watcher = new WorkflowProgressWatcher(client, tenantId)

      // Should not throw — gracefully handles null graph and finishes
      await watcher.watch(workflowRunId)

      const logs = (console.log as ReturnType<typeof vi.fn>).mock.calls
        .map((args: unknown[]) => args.join(' '))
        .join('\n')

      expect(logs).toContain('Workflow complete')
    })
  })
})
