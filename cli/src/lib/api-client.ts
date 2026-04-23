/**
 * HTTP client for the Analysi API.
 * Handles auth headers and Sifnos envelope unwrapping.
 */

import type { ApiResponse, Credentials } from './types.js'

export class ApiClient {
  private baseUrl: string
  private apiKey: string
  readonly apiVersion: string

  constructor(creds: Credentials, apiVersion = 'v1') {
    this.baseUrl = creds.base_url.replace(/\/+$/, '')
    this.apiKey = creds.api_key
    this.apiVersion = apiVersion
  }

  /**
   * Make an API request. Path should be relative (e.g., /alerts).
   * The tenant and API version are prepended automatically.
   */
  async request<T = unknown>(
    method: string,
    path: string,
    tenantId: string,
    options: {
      query?: Record<string, string | number | boolean | undefined>
      body?: unknown
    } = {},
  ): Promise<ApiResponse<T>> {
    const url = new URL(
      `${this.baseUrl}/${this.apiVersion}/${tenantId}${path}`,
    )

    // Add query params, filtering out undefined values
    if (options.query) {
      for (const [key, value] of Object.entries(options.query)) {
        if (value !== undefined) {
          url.searchParams.set(key, String(value))
        }
      }
    }

    const headers: Record<string, string> = {
      'X-API-Key': this.apiKey,
      'Content-Type': 'application/json',
      Accept: 'application/json',
    }

    const response = await fetch(url.toString(), {
      method,
      headers,
      body: options.body ? JSON.stringify(options.body) : undefined,
    })

    if (!response.ok) {
      const errorBody = await response.text()
      let detail = `HTTP ${response.status}: ${response.statusText}`
      try {
        const parsed = JSON.parse(errorBody)
        if (parsed.detail) {
          detail = typeof parsed.detail === 'string'
            ? parsed.detail
            : JSON.stringify(parsed.detail)
        }
      } catch {
        // Use default detail
      }

      throw new ApiError(detail, response.status)
    }

    // Handle 204 No Content (DELETE responses)
    if (response.status === 204) {
      return { data: null as T, meta: { request_id: '' } }
    }

    return (await response.json()) as ApiResponse<T>
  }

  /**
   * Make a platform-scoped API request (no tenant in path).
   * Used for /platform/v1/ endpoints.
   */
  async requestPlatform<T = unknown>(
    method: string,
    path: string,
    options: {
      query?: Record<string, string | number | boolean | undefined>
      body?: unknown
    } = {},
  ): Promise<ApiResponse<T>> {
    const url = new URL(`${this.baseUrl}/platform/v1${path}`)

    if (options.query) {
      for (const [key, value] of Object.entries(options.query)) {
        if (value !== undefined) {
          url.searchParams.set(key, String(value))
        }
      }
    }

    const headers: Record<string, string> = {
      'X-API-Key': this.apiKey,
      'Content-Type': 'application/json',
      Accept: 'application/json',
    }

    const response = await fetch(url.toString(), {
      method,
      headers,
      body: options.body ? JSON.stringify(options.body) : undefined,
    })

    if (!response.ok) {
      const errorBody = await response.text()
      let detail = `HTTP ${response.status}: ${response.statusText}`
      try {
        const parsed = JSON.parse(errorBody)
        if (parsed.detail) {
          detail = typeof parsed.detail === 'string'
            ? parsed.detail
            : JSON.stringify(parsed.detail)
        }
      } catch {
        // Use default detail
      }

      throw new ApiError(detail, response.status)
    }

    if (response.status === 204) {
      return { data: null as T, meta: { request_id: '' } }
    }

    return (await response.json()) as ApiResponse<T>
  }

  /**
   * Make a raw request (e.g., multipart form data for file uploads).
   * Does NOT set Content-Type — let the browser/runtime set it for FormData.
   */
  async requestRaw<T = unknown>(
    method: string,
    path: string,
    tenantId: string,
    formData: FormData,
  ): Promise<ApiResponse<T>> {
    const url = `${this.baseUrl}/${this.apiVersion}/${tenantId}${path}`

    const response = await fetch(url, {
      method,
      headers: {
        'X-API-Key': this.apiKey,
        Accept: 'application/json',
      },
      body: formData,
    })

    if (!response.ok) {
      const errorBody = await response.text()
      let detail = `HTTP ${response.status}: ${response.statusText}`
      try {
        const parsed = JSON.parse(errorBody)
        if (parsed.detail) {
          detail = typeof parsed.detail === 'string'
            ? parsed.detail
            : JSON.stringify(parsed.detail)
        }
      } catch {
        // Use default detail
      }

      throw new ApiError(detail, response.status)
    }

    return (await response.json()) as ApiResponse<T>
  }
}

export class ApiError extends Error {
  constructor(
    message: string,
    public statusCode: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}
