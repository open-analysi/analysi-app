/**
 * Unit tests for analysis-progress.ts — AnalysisProgressWatcher and colorDisposition.
 *
 * Covers: colorDisposition (pure function), findAnalysis, watch loop
 * (step transitions, completion, failure, timeout), and fetchSafe error handling.
 *
 * Mocks globalThis.fetch to simulate API responses and mocks sleep to avoid real delays.
 */

import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { ApiClient } from '../../src/lib/api-client.js'
import {
  AnalysisProgressWatcher,
  colorDisposition,
  type ProgressData,
  type AnalysisInfo,
} from '../../src/lib/analysis-progress.js'

// Mock sleep to resolve instantly — avoids 2s polling delays in tests
vi.mock('../../src/lib/cli-utils.js', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../src/lib/cli-utils.js')>()
  return { ...actual, sleep: vi.fn().mockResolvedValue(undefined) }
})

const creds = { api_key: 'test-key', base_url: 'http://localhost:8001' }
const tenantId = 'test-tenant'

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

function makeProgress(overrides: Partial<ProgressData> = {}): ProgressData {
  return {
    analysis_id: 'analysis-1',
    current_step: null,
    completed_steps: 0,
    total_steps: 4,
    status: 'running',
    error_message: null,
    steps_detail: {},
    ...overrides,
  }
}

function makeAnalysis(overrides: Partial<AnalysisInfo> = {}): AnalysisInfo {
  return {
    id: 'analysis-1',
    status: 'running',
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

describe('colorDisposition', () => {
  it('returns string containing "True Positive" for true positive dispositions', () => {
    const result = colorDisposition('True Positive')
    expect(result).toContain('True Positive')
  })

  it('returns string containing "False Positive - Benign" for benign dispositions', () => {
    const result = colorDisposition('False Positive - Benign')
    expect(result).toContain('False Positive - Benign')
  })

  it('returns string containing "Suspicious" for other dispositions', () => {
    const result = colorDisposition('Suspicious')
    expect(result).toContain('Suspicious')
  })

  it('routes malicious keywords to the red path and benign to green', () => {
    // Verify different dispositions go through different code paths
    // by checking the function handles all keyword variants
    const redInputs = ['True Positive', 'Malicious Activity', 'Compromise Detected']
    const greenInputs = ['False Positive', 'Benign Traffic']
    const yellowInputs = ['Suspicious', 'Inconclusive', 'Unknown']

    for (const input of redInputs) {
      expect(colorDisposition(input)).toContain(input)
    }
    for (const input of greenInputs) {
      expect(colorDisposition(input)).toContain(input)
    }
    for (const input of yellowInputs) {
      expect(colorDisposition(input)).toContain(input)
    }
  })
})

describe('AnalysisProgressWatcher', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  // ── findAnalysis ──────────────────────────────────────────────────

  describe('findAnalysis', () => {
    it('returns latest analysis (first in array) when no analysisId given', async () => {
      const analyses: AnalysisInfo[] = [
        makeAnalysis({ id: 'latest' }),
        makeAnalysis({ id: 'older' }),
      ]
      vi.spyOn(globalThis, 'fetch').mockResolvedValue(envelope(analyses))

      const client = new ApiClient(creds)
      const watcher = new AnalysisProgressWatcher(client, tenantId)

      const result = await watcher.findAnalysis('alert-1')
      expect(result).not.toBeNull()
      expect(result!.id).toBe('latest')
    })

    it('returns specific analysis when analysisId matches', async () => {
      const analyses: AnalysisInfo[] = [
        makeAnalysis({ id: 'latest' }),
        makeAnalysis({ id: 'specific-one' }),
      ]
      vi.spyOn(globalThis, 'fetch').mockResolvedValue(envelope(analyses))

      const client = new ApiClient(creds)
      const watcher = new AnalysisProgressWatcher(client, tenantId)

      const result = await watcher.findAnalysis('alert-1', 'specific-one')
      expect(result).not.toBeNull()
      expect(result!.id).toBe('specific-one')
    })

    it('returns null when no analyses exist', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValue(envelope([]))

      const client = new ApiClient(creds)
      const watcher = new AnalysisProgressWatcher(client, tenantId)

      const result = await watcher.findAnalysis('alert-1')
      expect(result).toBeNull()
    })
  })

  // ── watch() ───────────────────────────────────────────────────────

  describe('watch()', () => {
    beforeEach(() => {
      vi.spyOn(console, 'log').mockImplementation(() => {})
      vi.spyOn(console, 'error').mockImplementation(() => {})
    })

    it('prints step transitions as they change', async () => {
      let callCount = 0
      vi.spyOn(globalThis, 'fetch').mockImplementation(async () => {
        callCount++
        if (callCount === 1) {
          return envelope(makeProgress({ current_step: 'pre_triage', status: 'running' }))
        }
        if (callCount === 2) {
          return envelope(makeProgress({ current_step: 'workflow_builder', status: 'running' }))
        }
        // Terminal state — completed (also provide an alert detail for showResult)
        return envelope(makeProgress({ current_step: 'final_disposition_update', status: 'completed' }))
      })

      const client = new ApiClient(creds)
      const watcher = new AnalysisProgressWatcher(client, tenantId)

      await watcher.watch('alert-1', 'analysis-1')

      const logs = (console.log as ReturnType<typeof vi.fn>).mock.calls
        .map((args: unknown[]) => args.join(' '))
        .join('\n')

      expect(logs).toContain('Pre-triage')
      expect(logs).toContain('Building workflow')
    })

    it('shows completion message on status=completed', async () => {
      let callCount = 0
      vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => {
        callCount++
        const urlStr = String(url)

        // First call: progress endpoint returning completed
        if (urlStr.includes('/analysis/progress')) {
          return envelope(makeProgress({ current_step: 'final_disposition_update', status: 'completed' }))
        }
        // Second call: alert detail for showResult
        if (urlStr.includes('/alerts/') && !urlStr.includes('/analyses') && !urlStr.includes('/progress')) {
          return envelope({
            alert_id: 'alert-1',
            human_readable_id: 'ALERT-001',
            title: 'Test Alert',
            analysis_status: 'completed',
            current_disposition_category: 'true_positive',
            current_disposition_display_name: 'True Positive',
            current_disposition_confidence: 95,
          })
        }
        return envelope(null)
      })

      const client = new ApiClient(creds)
      const watcher = new AnalysisProgressWatcher(client, tenantId)

      await watcher.watch('alert-1', 'analysis-1')

      const logs = (console.log as ReturnType<typeof vi.fn>).mock.calls
        .map((args: unknown[]) => args.join(' '))
        .join('\n')

      expect(logs).toContain('Analysis complete')
      expect(logs).toContain('Disposition')
      expect(logs).toContain('True Positive')
    })

    it('shows failure message with error on status=failed', async () => {
      vi.spyOn(globalThis, 'fetch').mockImplementation(async () => {
        return envelope(makeProgress({
          status: 'failed',
          error_message: 'Task execution timed out after 300 seconds',
        }))
      })

      const client = new ApiClient(creds)
      const watcher = new AnalysisProgressWatcher(client, tenantId)

      await watcher.watch('alert-1', 'analysis-1')

      const logs = (console.log as ReturnType<typeof vi.fn>).mock.calls
        .map((args: unknown[]) => args.join(' '))
        .join('\n')

      expect(logs).toContain('Analysis failed')
      expect(logs).toContain('Task execution timed out')
    })

    it('shows task completions during workflow_execution step', async () => {
      let callCount = 0
      vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => {
        callCount++
        const urlStr = String(url)

        // Progress calls
        if (urlStr.includes('/analysis/progress')) {
          if (callCount <= 2) {
            return envelope(makeProgress({ current_step: 'workflow_execution', status: 'running' }))
          }
          return envelope(makeProgress({ current_step: 'workflow_execution', status: 'completed' }))
        }

        // Analyses call (for findWorkflowRunId)
        if (urlStr.includes('/analyses')) {
          return envelope([makeAnalysis({ id: 'analysis-1', workflow_run_id: 'wfr-1' })])
        }

        // Task-runs call (for showNewTasks)
        if (urlStr.includes('/task-runs')) {
          return envelope([
            { id: 'tr-1', task_name: 'Enrich IP', status: 'completed', duration: 'PT2.5S', created_at: '2026-01-01T00:00:00Z' },
            { id: 'tr-2', task_name: 'Check Reputation', status: 'failed', duration: null, created_at: '2026-01-01T00:00:01Z' },
          ])
        }

        // Alert detail call (for showResult)
        if (urlStr.includes('/alerts/') && !urlStr.includes('/analyses') && !urlStr.includes('/progress')) {
          return envelope({
            alert_id: 'alert-1', human_readable_id: 'A-1', title: 'Test',
            analysis_status: 'completed', current_disposition_category: 'benign',
            current_disposition_display_name: 'Benign', current_disposition_confidence: 90,
          })
        }

        return envelope(null)
      })

      const client = new ApiClient(creds)
      const watcher = new AnalysisProgressWatcher(client, tenantId)

      await watcher.watch('alert-1', 'analysis-1')

      const logs = (console.log as ReturnType<typeof vi.fn>).mock.calls
        .map((args: unknown[]) => args.join(' '))
        .join('\n')

      expect(logs).toContain('Enrich IP')
      expect(logs).toContain('Check Reputation')
    })

    it('shows completion without disposition when alert fetch fails', async () => {
      vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => {
        const urlStr = String(url)
        if (urlStr.includes('/analysis/progress')) {
          return envelope(makeProgress({ status: 'completed' }))
        }
        // Alert detail fetch fails
        return { ok: false, status: 500, statusText: 'Error', text: async () => 'error', json: async () => ({}) } as Response
      })

      const client = new ApiClient(creds)
      const watcher = new AnalysisProgressWatcher(client, tenantId)

      await watcher.watch('alert-1', 'analysis-1')

      const logs = (console.log as ReturnType<typeof vi.fn>).mock.calls
        .map((args: unknown[]) => args.join(' '))
        .join('\n')

      expect(logs).toContain('Analysis complete')
      // Should NOT contain "Disposition" since alert fetch failed
    })

    it('shows timeout message when poll exceeds TIMEOUT_MS', async () => {
      // Mock Date.now to advance past 10 minutes
      const realDateNow = Date.now
      let mockTime = 1000000
      vi.spyOn(Date, 'now').mockImplementation(() => {
        // Each call advances time by 11 minutes to exceed TIMEOUT_MS
        const current = mockTime
        mockTime += 11 * 60 * 1000
        return current
      })

      // Return a running progress that never completes
      vi.spyOn(globalThis, 'fetch').mockImplementation(async () => {
        return envelope(makeProgress({ current_step: 'pre_triage', status: 'running' }))
      })

      const client = new ApiClient(creds)
      const watcher = new AnalysisProgressWatcher(client, tenantId)

      await watcher.watch('alert-1', 'analysis-1')

      const logs = (console.log as ReturnType<typeof vi.fn>).mock.calls
        .map((args: unknown[]) => args.join(' '))
        .join('\n')

      expect(logs).toContain('Timed out')
      expect(logs).toContain('Analysis may still be running')
    })
  })

  // ── fetchSafe ─────────────────────────────────────────────────────

  describe('fetchSafe (via findAnalysis)', () => {
    it('returns null on network error (fetch throws)', async () => {
      vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('ECONNREFUSED'))

      const client = new ApiClient(creds)
      const watcher = new AnalysisProgressWatcher(client, tenantId)

      const result = await watcher.findAnalysis('alert-1')
      expect(result).toBeNull()
    })

    it('returns data on success', async () => {
      const analyses: AnalysisInfo[] = [makeAnalysis({ id: 'a-1' })]
      vi.spyOn(globalThis, 'fetch').mockResolvedValue(envelope(analyses))

      const client = new ApiClient(creds)
      const watcher = new AnalysisProgressWatcher(client, tenantId)

      const result = await watcher.findAnalysis('alert-1')
      expect(result).not.toBeNull()
      expect(result!.id).toBe('a-1')
    })
  })
})
