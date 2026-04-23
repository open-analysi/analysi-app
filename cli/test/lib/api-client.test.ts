/**
 * Unit tests for api-client.ts — ApiClient and ApiError.
 *
 * Covers: constructor, URL construction, headers, response handling,
 * error handling, requestPlatform(), requestRaw(), and ApiError class.
 */

import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { ApiClient, ApiError } from '../../src/lib/api-client.js'
import type { Credentials } from '../../src/lib/types.js'

function mockFetch(body: unknown, status = 200, ok = true) {
  return vi.spyOn(globalThis, 'fetch').mockResolvedValue({
    ok,
    status,
    statusText: ok ? 'OK' : 'Error',
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as Response)
}

const CREDS: Credentials = {
  api_key: 'test-api-key-123',
  base_url: 'https://api.example.com',
  default_tenant: 'tenant-1',
}

describe('ApiClient', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  // ── Constructor ──────────────────────────────────────────────────

  describe('constructor', () => {
    it('strips trailing slashes from base_url', () => {
      const client = new ApiClient({
        ...CREDS,
        base_url: 'https://api.example.com///',
      })
      const spy = mockFetch({ data: null, meta: { request_id: '1' } })

      client.request('GET', '/test', 'tenant-1')

      const calledUrl = spy.mock.calls[0]![0] as string
      expect(calledUrl).toMatch(/^https:\/\/api\.example\.com\/v1\//)
      expect(calledUrl).not.toMatch(/\/\/\/v1/)
    })

    it('defaults apiVersion to v1', () => {
      const client = new ApiClient(CREDS)
      expect(client.apiVersion).toBe('v1')
    })
  })

  // ── request() — URL construction ─────────────────────────────────

  describe('request() — URL construction', () => {
    it('builds correct URL: {baseUrl}/{apiVersion}/{tenantId}{path}', async () => {
      const spy = mockFetch({ data: [], meta: { request_id: 'r1' } })
      const client = new ApiClient(CREDS)

      await client.request('GET', '/alerts', 'tenant-abc')

      const calledUrl = spy.mock.calls[0]![0] as string
      expect(calledUrl).toBe('https://api.example.com/v1/tenant-abc/alerts')
    })

    it('adds query params, filtering out undefined values', async () => {
      const spy = mockFetch({ data: [], meta: { request_id: 'r2' } })
      const client = new ApiClient(CREDS)

      await client.request('GET', '/alerts', 'tenant-1', {
        query: { status: 'open', severity: undefined, limit: '10' },
      })

      const calledUrl = new URL(spy.mock.calls[0]![0] as string)
      expect(calledUrl.searchParams.get('status')).toBe('open')
      expect(calledUrl.searchParams.get('limit')).toBe('10')
      expect(calledUrl.searchParams.has('severity')).toBe(false)
    })

    it('encodes boolean and numeric query params as strings', async () => {
      const spy = mockFetch({ data: [], meta: { request_id: 'r3' } })
      const client = new ApiClient(CREDS)

      await client.request('GET', '/items', 'tenant-1', {
        query: { active: true, count: 42 },
      })

      const calledUrl = new URL(spy.mock.calls[0]![0] as string)
      expect(calledUrl.searchParams.get('active')).toBe('true')
      expect(calledUrl.searchParams.get('count')).toBe('42')
    })
  })

  // ── request() — headers ──────────────────────────────────────────

  describe('request() — headers', () => {
    it('sends X-API-Key, Content-Type, and Accept headers', async () => {
      const spy = mockFetch({ data: {}, meta: { request_id: 'r4' } })
      const client = new ApiClient(CREDS)

      await client.request('GET', '/alerts', 'tenant-1')

      const options = spy.mock.calls[0]![1] as RequestInit
      const headers = options.headers as Record<string, string>
      expect(headers['X-API-Key']).toBe('test-api-key-123')
      expect(headers['Content-Type']).toBe('application/json')
      expect(headers['Accept']).toBe('application/json')
    })

    it('sends JSON-stringified body for POST/PUT', async () => {
      const spy = mockFetch({ data: { id: '1' }, meta: { request_id: 'r5' } })
      const client = new ApiClient(CREDS)
      const payload = { name: 'New Alert', severity: 'high' }

      await client.request('POST', '/alerts', 'tenant-1', { body: payload })

      const options = spy.mock.calls[0]![1] as RequestInit
      expect(options.method).toBe('POST')
      expect(options.body).toBe(JSON.stringify(payload))
    })
  })

  // ── request() — response handling ────────────────────────────────

  describe('request() — response handling', () => {
    it('returns unwrapped Sifnos envelope {data, meta}', async () => {
      const envelope = {
        data: [{ id: '1', name: 'Alert A' }],
        meta: { request_id: 'req-123', total: 1, limit: 25, offset: 0 },
      }
      mockFetch(envelope)
      const client = new ApiClient(CREDS)

      const result = await client.request('GET', '/alerts', 'tenant-1')

      expect(result.data).toEqual([{ id: '1', name: 'Alert A' }])
      expect(result.meta.request_id).toBe('req-123')
      expect(result.meta.total).toBe(1)
    })

    it('handles 204 No Content (returns null data)', async () => {
      mockFetch(null, 204, true)
      const client = new ApiClient(CREDS)

      const result = await client.request('DELETE', '/alerts/123', 'tenant-1')

      expect(result.data).toBeNull()
      expect(result.meta.request_id).toBe('')
    })
  })

  // ── request() — error handling ───────────────────────────────────

  describe('request() — error handling', () => {
    it('throws ApiError with status code on non-ok response', async () => {
      mockFetch({ detail: 'Not found' }, 404, false)
      const client = new ApiClient(CREDS)

      await expect(
        client.request('GET', '/alerts/999', 'tenant-1'),
      ).rejects.toThrow(ApiError)

      try {
        await client.request('GET', '/alerts/999', 'tenant-1')
        expect.fail('should have thrown')
      } catch (err) {
        expect(err).toBeInstanceOf(ApiError)
        expect((err as ApiError).statusCode).toBe(404)
      }
    })

    it('extracts detail string from error body JSON', async () => {
      mockFetch({ detail: 'Tenant not authorized' }, 403, false)
      const client = new ApiClient(CREDS)

      try {
        await client.request('GET', '/secrets', 'tenant-1')
        expect.fail('should have thrown')
      } catch (err) {
        expect((err as ApiError).message).toBe('Tenant not authorized')
      }
    })

    it('falls back to HTTP {status}: {statusText} when error body is not JSON', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValue({
        ok: false,
        status: 502,
        statusText: 'Bad Gateway',
        json: async () => { throw new Error('not json') },
        text: async () => 'upstream connect error',
      } as Response)
      const client = new ApiClient(CREDS)

      try {
        await client.request('GET', '/alerts', 'tenant-1')
        expect.fail('should have thrown')
      } catch (err) {
        expect((err as ApiError).message).toBe('HTTP 502: Bad Gateway')
        expect((err as ApiError).statusCode).toBe(502)
      }
    })
  })

  // ── requestPlatform() ────────────────────────────────────────────

  describe('requestPlatform()', () => {
    it('uses /platform/v1 path prefix (no tenant)', async () => {
      const spy = mockFetch({ data: { healthy: true }, meta: { request_id: 'p1' } })
      const client = new ApiClient(CREDS)

      await client.requestPlatform('GET', '/health')

      const calledUrl = spy.mock.calls[0]![0] as string
      expect(calledUrl).toBe('https://api.example.com/platform/v1/health')
    })

    it('sends same auth headers', async () => {
      const spy = mockFetch({ data: {}, meta: { request_id: 'p2' } })
      const client = new ApiClient(CREDS)

      await client.requestPlatform('GET', '/tenants')

      const options = spy.mock.calls[0]![1] as RequestInit
      const headers = options.headers as Record<string, string>
      expect(headers['X-API-Key']).toBe('test-api-key-123')
      expect(headers['Content-Type']).toBe('application/json')
      expect(headers['Accept']).toBe('application/json')
    })

    it('throws ApiError on non-ok response', async () => {
      mockFetch({ detail: 'Forbidden' }, 403, false)
      const client = new ApiClient(CREDS)

      await expect(
        client.requestPlatform('GET', '/tenants'),
      ).rejects.toThrow(ApiError)
    })

    it('handles 204 No Content', async () => {
      mockFetch(null, 204, true)
      const client = new ApiClient(CREDS)

      const result = await client.requestPlatform('DELETE', '/tenants/abc')
      expect(result.data).toBeNull()
    })

    it('adds query params', async () => {
      const spy = mockFetch({ data: [], meta: { request_id: 'p3' } })
      const client = new ApiClient(CREDS)

      await client.requestPlatform('GET', '/tenants', {
        query: { active: true, limit: 10, unused: undefined },
      })

      const calledUrl = new URL(spy.mock.calls[0]![0] as string)
      expect(calledUrl.searchParams.get('active')).toBe('true')
      expect(calledUrl.searchParams.get('limit')).toBe('10')
      expect(calledUrl.searchParams.has('unused')).toBe(false)
    })

    it('sends JSON body for POST', async () => {
      const spy = mockFetch({ data: { id: 't1' }, meta: { request_id: 'p4' } })
      const client = new ApiClient(CREDS)
      const body = { name: 'new-tenant' }

      await client.requestPlatform('POST', '/tenants', { body })

      const options = spy.mock.calls[0]![1] as RequestInit
      expect(options.body).toBe(JSON.stringify(body))
    })

    it('falls back to HTTP status text for non-JSON error body', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValue({
        ok: false, status: 503, statusText: 'Service Unavailable',
        json: async () => { throw new Error('not json') },
        text: async () => '<html>down</html>',
      } as Response)
      const client = new ApiClient(CREDS)

      try {
        await client.requestPlatform('GET', '/health')
        expect.fail('should have thrown')
      } catch (err) {
        expect((err as ApiError).message).toBe('HTTP 503: Service Unavailable')
      }
    })
  })

  // ── requestRaw() ─────────────────────────────────────────────────

  describe('requestRaw()', () => {
    it('does NOT set Content-Type header (for FormData)', async () => {
      const spy = mockFetch({ data: { uploaded: true }, meta: { request_id: 'raw1' } })
      const client = new ApiClient(CREDS)
      const formData = new FormData()
      formData.append('file', new Blob(['test']), 'test.txt')

      await client.requestRaw('POST', '/upload', 'tenant-1', formData)

      const options = spy.mock.calls[0]![1] as RequestInit
      const headers = options.headers as Record<string, string>
      expect(headers['Content-Type']).toBeUndefined()
    })

    it('still sends X-API-Key and Accept headers', async () => {
      const spy = mockFetch({ data: { uploaded: true }, meta: { request_id: 'raw2' } })
      const client = new ApiClient(CREDS)
      const formData = new FormData()
      formData.append('file', new Blob(['data']), 'data.csv')

      await client.requestRaw('POST', '/upload', 'tenant-1', formData)

      const options = spy.mock.calls[0]![1] as RequestInit
      const headers = options.headers as Record<string, string>
      expect(headers['X-API-Key']).toBe('test-api-key-123')
      expect(headers['Accept']).toBe('application/json')
    })

    it('throws ApiError on non-ok response', async () => {
      mockFetch({ detail: 'File too large' }, 413, false)
      const client = new ApiClient(CREDS)
      const formData = new FormData()
      formData.append('file', new Blob(['big']), 'big.bin')

      try {
        await client.requestRaw('POST', '/upload', 'tenant-1', formData)
        expect.fail('should have thrown')
      } catch (err) {
        expect(err).toBeInstanceOf(ApiError)
        expect((err as ApiError).statusCode).toBe(413)
        expect((err as ApiError).message).toBe('File too large')
      }
    })

    it('extracts structured detail from error body', async () => {
      mockFetch({ detail: { loc: ['body', 'file'], msg: 'invalid format' } }, 422, false)
      const client = new ApiClient(CREDS)
      const formData = new FormData()

      try {
        await client.requestRaw('POST', '/upload', 'tenant-1', formData)
        expect.fail('should have thrown')
      } catch (err) {
        // Non-string detail gets JSON.stringified
        expect((err as ApiError).message).toContain('invalid format')
      }
    })

    it('builds correct URL with tenant and API version', async () => {
      const spy = mockFetch({ data: {}, meta: { request_id: 'raw3' } })
      const client = new ApiClient(CREDS)
      const formData = new FormData()

      await client.requestRaw('POST', '/files', 'my-tenant', formData)

      const calledUrl = spy.mock.calls[0]![0] as string
      expect(calledUrl).toBe('https://api.example.com/v1/my-tenant/files')
    })
  })
})

// ── ApiError ─────────────────────────────────────────────────────

describe('ApiError', () => {
  it('has name="ApiError", carries message and statusCode', () => {
    const error = new ApiError('Something went wrong', 500)

    expect(error).toBeInstanceOf(Error)
    expect(error).toBeInstanceOf(ApiError)
    expect(error.name).toBe('ApiError')
    expect(error.message).toBe('Something went wrong')
    expect(error.statusCode).toBe(500)
  })
})
