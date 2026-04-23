/**
 * Tests for config-loader.ts — resolvePath, loadCliConfig, getOperationConfig.
 */

import { describe, it, expect } from 'vitest'
import { resolvePath, loadCliConfig, getOperationConfig } from '../../src/lib/config-loader.js'

describe('resolvePath', () => {
  it('resolves a single placeholder', () => {
    expect(resolvePath('/alerts/{alert_id}', { alert_id: 'abc-123' })).toBe(
      '/alerts/abc-123',
    )
  })

  it('resolves multiple placeholders', () => {
    const result = resolvePath('/alerts/{alert_id}/analyses/{analysis_id}', {
      alert_id: 'a1',
      analysis_id: 'x9',
    })
    expect(result).toBe('/alerts/a1/analyses/x9')
  })

  it('URL-encodes special characters in values', () => {
    expect(resolvePath('/alerts/{alert_id}', { alert_id: 'foo bar/baz' })).toBe(
      '/alerts/foo%20bar%2Fbaz',
    )
  })

  it('throws for a missing argument', () => {
    expect(() => resolvePath('/alerts/{alert_id}', {})).toThrow(
      'Missing required argument: alert_id',
    )
  })

  it('leaves non-template parts unchanged', () => {
    expect(resolvePath('/static/path', {})).toBe('/static/path')
  })

  it('handles numeric-looking values', () => {
    expect(resolvePath('/items/{id}', { id: '12345' })).toBe('/items/12345')
  })
})

describe('loadCliConfig', () => {
  it('loads and parses cli-config.yaml', () => {
    const config = loadCliConfig()
    expect(config).toBeDefined()
    expect(config.cli).toBeDefined()
    expect(config.cli.name).toBe('analysi')
    expect(config.commands).toBeDefined()
    expect(typeof config.commands).toBe('object')
  })

  it('returns cached config on second call', () => {
    const first = loadCliConfig()
    const second = loadCliConfig()
    expect(first).toBe(second) // same reference = cached
  })

  it('contains expected command topics', () => {
    const config = loadCliConfig()
    expect(config.commands.alerts).toBeDefined()
    expect(config.commands.tasks).toBeDefined()
    expect(config.commands.workflows).toBeDefined()
  })
})

describe('getOperationConfig', () => {
  it('returns operation config for a known topic and command', () => {
    const op = getOperationConfig('alerts', 'list')
    expect(op).toBeDefined()
    expect(op!.method).toBe('GET')
    expect(op!.path).toBeDefined()
  })

  it('returns undefined for unknown topic', () => {
    const op = getOperationConfig('nonexistent', 'list')
    expect(op).toBeUndefined()
  })

  it('returns undefined for unknown command in valid topic', () => {
    const op = getOperationConfig('alerts', 'nonexistent')
    expect(op).toBeUndefined()
  })
})
