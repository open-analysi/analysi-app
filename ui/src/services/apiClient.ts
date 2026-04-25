/* eslint-disable @typescript-eslint/prefer-promise-reject-errors */
import axios, { type AxiosError, type AxiosRequestConfig } from 'axios';

import { useAuthStore } from '../store/authStore';
import { logger, type ErrorContext } from '../utils/errorHandler';

// ==================== UUID & Template Helpers ====================

// UUID validation helper - accepts any UUID-like string (8-4-4-4-12 hex pattern)
// Note: We use a permissive pattern that accepts all UUID formats including
// system template UUIDs like 00000000-0000-0000-0000-000000000001
const UUID_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export function isValidUuid(value: string): boolean {
  return UUID_REGEX.test(value);
}

// Built-in transformation templates mapped to their system template UUIDs
// These are seeded in the backend database (V044__seed_system_node_templates.sql)
// The frontend uses short names like 'identity', but the backend expects UUID references
export const BUILTIN_TEMPLATE_UUIDS: Record<string, string> = {
  identity: '00000000-0000-0000-0000-000000000001', // system_identity
  merge: '00000000-0000-0000-0000-000000000002', // system_merge
  collect: '00000000-0000-0000-0000-000000000003', // system_collect
};

/**
 * Resolve node_template_id to a valid UUID:
 * - If already a UUID: return as-is
 * - If a built-in name (identity/merge/collect): return system template UUID
 * - Otherwise: return undefined
 */
export function resolveNodeTemplateId(nodeTemplateId: string | undefined): string | undefined {
  if (!nodeTemplateId) return undefined;
  if (isValidUuid(nodeTemplateId)) return nodeTemplateId;
  return BUILTIN_TEMPLATE_UUIDS[nodeTemplateId];
}

// ==================== Axios Instance ====================

// Create a separate axios instance for the backend API
// Detect environment and compose URL with tenant
const getBaseURL = () => {
  // Browser: use proxy path. Tenant is injected per-request by the
  // interceptor below (from the JWT-derived authStore.tenant_id).
  if (
    typeof window !== 'undefined' &&
    !(typeof process !== 'undefined' && process.env?.NODE_ENV === 'test')
  ) {
    return '/api';
  }
  // Test / Node.js scripts only — requires VITE_BACKEND_API_TENANT in .env.test
  const baseUrl = import.meta.env.VITE_BACKEND_API_URL || 'http://localhost:8001';
  const tenant = import.meta.env.VITE_BACKEND_API_TENANT || 'default';
  return `${baseUrl}/v1/${tenant}`;
};

export const backendApiClient = axios.create({
  baseURL: getBaseURL(),
  paramsSerializer: (params: Record<string, unknown>) => {
    // Serialize arrays as repeated keys (FastAPI style: categories=a&categories=b)
    // instead of axios default (categories[]=a&categories[]=b)
    const parts: string[] = [];
    for (const [key, value] of Object.entries(params)) {
      if (Array.isArray(value)) {
        for (const v of value as string[]) {
          parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(String(v))}`);
        }
      } else if (value != null) {
        parts.push(
          `${encodeURIComponent(key)}=${encodeURIComponent(value as string | number | boolean)}`
        );
      }
    }
    return parts.join('&');
  },
});

// In browser mode, inject the tenant_id and Bearer token from authStore.
// In test/Node.js mode this interceptor is skipped — the static baseURL is used.
const isBrowser =
  typeof window !== 'undefined' &&
  !(typeof process !== 'undefined' && process.env?.NODE_ENV === 'test');

// API key for auth-disabled mode.
// Browser (E2E): read from VITE_E2E_API_KEY (injected by Vite).
// Node.js (integration test scripts): read from ANALYSI_SYSTEM_API_KEY env var.
function getE2eApiKey(): string | undefined {
  if (isBrowser) {
    return import.meta.env.VITE_E2E_API_KEY as string | undefined;
  }
  if (typeof process !== 'undefined') {
    return process.env.ANALYSI_SYSTEM_API_KEY;
  }
  return undefined;
}
const E2E_API_KEY = getE2eApiKey();

if (isBrowser) {
  backendApiClient.interceptors.request.use((config) => {
    const { tenant_id, accessToken } = useAuthStore.getState();
    config.baseURL = `/api/v1/${tenant_id}`;
    if (accessToken) {
      config.headers.Authorization = `Bearer ${accessToken}`;
    } else if (E2E_API_KEY) {
      config.headers['X-API-Key'] = E2E_API_KEY;
    }
    // Note: created_by is now a UUID FK to the users table.
    // The backend resolves the user identity from the JWT token automatically,
    // so we no longer need to inject it into request bodies.
    return config;
  });
}

// Add request and response interceptors for logging
backendApiClient.interceptors.request.use(
  (config) => {
    logger.debug(
      `Request: ${config.method?.toUpperCase()} ${config.url}`,
      config.data || config.params,
      { component: 'ApiClient', method: 'request' }
    );
    return config;
  },
  (error) => {
    logger.error('Request error', error, { component: 'ApiClient', method: 'request' });
    return Promise.reject(error);
  }
);

backendApiClient.interceptors.response.use(
  (response) => {
    logger.debug(`Response: ${response.status} ${response.config.url}`, response.data, {
      component: 'ApiClient',
      method: 'response',
    });
    return response;
  },
  (error: unknown) => {
    logger.error('Response error', error, { component: 'ApiClient', method: 'response' });
    if (error && typeof error === 'object' && 'response' in error) {
      const axiosError = error as { response: { status: number; data: unknown } };
      const responseData = axiosError.response.data as Record<string, unknown> | undefined;
      if (responseData && typeof responseData === 'object') {
        // RFC 9457 Problem Details — backend returns application/problem+json
        // with: { type, title, status, detail, request_id, errors? }
        const requestId = responseData.request_id as string | undefined;
        const detail = responseData.detail as string | undefined;
        const title = responseData.title as string | undefined;

        if (axiosError.response.status === 422) {
          const errors = responseData.errors as unknown[] | undefined;
          logger.error('Validation errors', errors ?? detail ?? responseData, {
            component: 'ApiClient',
            method: 'response',
            action: '422 validation',
            ...(requestId && { requestId }),
          });
        } else if (axiosError.response.status >= 400) {
          logger.error(`${title ?? 'API error'}: ${detail ?? ''}`, responseData, {
            component: 'ApiClient',
            method: 'response',
            action: `${axiosError.response.status} error`,
            ...(requestId && { requestId }),
          });
        }
      }
    }
    return Promise.reject(error);
  }
);

// ==================== Sifnos Envelope Types ====================

/** Shape of every Sifnos-envelope response from the backend */
export interface SifnosEnvelope<T = unknown> {
  data: T;
  meta: {
    request_id?: string;
    total?: number;
    limit?: number;
    offset?: number;
    [key: string]: unknown;
  };
}

/** RFC 9457 Problem Details response from the backend */
export interface ProblemDetail {
  type?: string;
  title?: string;
  status?: number;
  detail?: string;
  request_id?: string;
  errors?: Array<{ loc?: unknown[]; msg?: string; message?: string; type?: string }>;
  [key: string]: unknown;
}

/**
 * Extract a human-readable error message from an API error.
 *
 * Handles RFC 9457 Problem Details (Sifnos) as well as legacy
 * FastAPI `{detail}` responses for backward compatibility.
 */
export function extractApiErrorMessage(error: unknown, fallback = 'An error occurred'): string {
  if (!error || typeof error !== 'object') return fallback;
  const axiosErr = error as { response?: { data?: Record<string, unknown> }; message?: string };
  const data = axiosErr.response?.data;
  if (!data || typeof data !== 'object') return axiosErr.message || fallback;

  // RFC 9457: { detail: string, errors?: [...] }
  const problem = data as ProblemDetail;

  // Validation errors (422) — array of field-level issues
  if (Array.isArray(problem.errors) && problem.errors.length > 0) {
    return problem.errors.map((e) => e.msg || e.message || JSON.stringify(e)).join(', ');
  }

  // Simple string detail (most error responses)
  if (typeof problem.detail === 'string') return problem.detail;

  // Legacy: detail was an array (old FastAPI format)
  if (Array.isArray(problem.detail)) {
    return (problem.detail as Array<{ msg?: string; message?: string }>)
      .map((e) => e.msg || e.message || JSON.stringify(e))
      .join(', ');
  }

  // Legacy: detail was an object with msg/message
  if (problem.detail && typeof problem.detail === 'object') {
    const d = problem.detail as { msg?: string; message?: string };
    if (d.msg) return d.msg;
    if (d.message) return d.message;
  }

  if (typeof problem.title === 'string') return problem.title;
  return axiosErr.message || fallback;
}

// ==================== Sifnos Envelope Helpers ====================
//
// All backend endpoints return { data: T, meta: { request_id, total?, ... } }.
// These helpers unwrap the envelope so service functions stay concise.
//
// Pattern A (lists)  → fetchList<T>('/items', 'items')  => { items: T[], total }
// Pattern B (single) → fetchOne<T>('/items/123')        => T
// Mutations          → mutateOne<T>(post, '/items', body) => T
// Void actions       → apiDelete('/items/123')          => void

/**
 * Centralized error-handling wrapper for API calls.
 * Eliminates the repeated try/catch/log/rethrow pattern in every service function.
 */
export async function withApi<T>(
  method: string,
  action: string,
  fn: () => Promise<T>,
  contextOverrides?: Partial<ErrorContext>
): Promise<T> {
  const context: ErrorContext = {
    component: 'ApiService',
    method,
    action,
    ...contextOverrides,
  };
  try {
    const result = await fn();
    logger.debug(`Success: ${action}`, {}, context);
    return result;
  } catch (error) {
    logger.error(`Failed: ${action}`, error as AxiosError, context);
    throw error;
  }
}

/**
 * Fetch a single item from a GET endpoint.
 * Unwraps Sifnos envelope: response.data.data → T
 */
export async function fetchOne<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
  const response = config
    ? await backendApiClient.get<SifnosEnvelope<T>>(url, config)
    : await backendApiClient.get<SifnosEnvelope<T>>(url);
  return response.data.data;
}

/**
 * Fetch a paginated list from a GET endpoint.
 * Unwraps Sifnos envelope: { data: T[], meta: { total } } → { [key]: T[], total }
 */
export async function fetchList<K extends string, T>(
  url: string,
  key: K,
  config?: AxiosRequestConfig
): Promise<Record<K, T[]> & { total: number }> {
  const response = config
    ? await backendApiClient.get<SifnosEnvelope<T[]>>(url, config)
    : await backendApiClient.get<SifnosEnvelope<T[]>>(url);
  const { data, meta } = response.data;
  return { [key]: data, total: meta?.total ?? (data?.length || 0) } as Record<K, T[]> & {
    total: number;
  };
}

/**
 * POST/PUT/PATCH that returns a single item.
 * Unwraps Sifnos envelope: response.data.data → T
 */
export async function mutateOne<T>(
  method: 'post' | 'put' | 'patch',
  url: string,
  body?: unknown,
  config?: AxiosRequestConfig
): Promise<T> {
  let response;
  if (config) {
    response = await backendApiClient[method]<SifnosEnvelope<T>>(url, body, config);
  } else if (body !== undefined) {
    response = await backendApiClient[method]<SifnosEnvelope<T>>(url, body);
  } else {
    response = await backendApiClient[method]<SifnosEnvelope<T>>(url);
  }
  return response.data.data;
}

/**
 * DELETE that returns void.
 */
export async function apiDelete(url: string): Promise<void> {
  await backendApiClient.delete(url);
}
