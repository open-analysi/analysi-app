/**
 * Tests for cli-utils.ts — elapsed time, ISO-8601 duration formatting, sleep.
 */

import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { elapsed, formatDuration, sleep } from '../../src/lib/cli-utils.js'

describe('elapsed', () => {
  let nowSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    nowSpy = vi.spyOn(Date, 'now')
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('returns milliseconds for durations under 1 second', () => {
    const start = 1000
    nowSpy.mockReturnValue(1350)
    expect(elapsed(start)).toBe('350ms')
  })

  it('returns seconds for durations under 60 seconds', () => {
    const start = 1000
    nowSpy.mockReturnValue(13000)
    expect(elapsed(start)).toBe('12s')
  })

  it('returns minutes and seconds for durations >= 60 seconds', () => {
    const start = 1000
    nowSpy.mockReturnValue(136000) // 135000ms = 2m 15s
    expect(elapsed(start)).toBe('2m 15s')
  })

  it('returns "0ms" when called at the same instant', () => {
    const start = 5000
    nowSpy.mockReturnValue(5000)
    expect(elapsed(start)).toBe('0ms')
  })
})

describe('formatDuration', () => {
  it('returns empty string for null input', () => {
    expect(formatDuration(null)).toBe('')
  })

  it('parses full ISO-8601 duration with hours, minutes, and seconds', () => {
    expect(formatDuration('PT1H2M3.4S')).toBe('1h 2m 3.4s')
  })

  it('parses seconds-only duration', () => {
    expect(formatDuration('PT30S')).toBe('30.0s')
  })

  it('parses minutes-only duration (seconds always appended)', () => {
    expect(formatDuration('PT5M')).toBe('5m 0.0s')
  })

  it('returns raw string for non-matching input', () => {
    expect(formatDuration('invalid')).toBe('invalid')
  })

  it('parses sub-second duration', () => {
    expect(formatDuration('PT0.5S')).toBe('0.5s')
  })
})

describe('sleep', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('returns a promise that resolves after the given delay', async () => {
    const promise = sleep(500)
    vi.advanceTimersByTime(500)
    await expect(promise).resolves.toBeUndefined()
  })
})
