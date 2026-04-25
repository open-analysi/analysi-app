/**
 * Shared types for the Analysi CLI.
 * DO NOT EDIT — foundational types used across the CLI.
 */

export interface CliConfig {
  cli: {
    name: string
    description: string
    base_url: string
    api_version: string
  }
  commands: Record<string, TopicConfig>
}

export interface TopicConfig {
  description: string
  operations: Record<string, OperationConfig>
}

export interface OperationConfig {
  description: string
  method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  path: string
  args?: Record<string, ArgConfig>
  flags?: Record<string, FlagConfig>
}

export interface ArgConfig {
  required?: boolean
  description: string
}

export interface FlagConfig {
  type: 'string' | 'integer' | 'boolean'
  description: string
  required?: boolean
  default?: string | number | boolean
  options?: string[]
}

export interface Credentials {
  api_key: string
  base_url: string
  default_tenant?: string
}

/** Sifnos envelope — all API responses are wrapped in this. */
export interface ApiResponse<T = unknown> {
  data: T
  meta: {
    request_id: string
    total?: number
    limit?: number
    offset?: number
  }
}
