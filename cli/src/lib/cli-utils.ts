/**
 * Shared CLI utilities — timing, duration formatting, sleep.
 *
 * Centralises helpers used across progress watchers and hand-written commands
 * so they stay consistent and aren't duplicated.
 */

/**
 * Human-readable elapsed time since `startTime`.
 * Returns "350ms", "12s", or "2m 15s".
 */
export function elapsed(startTime: number): string {
  const ms = Date.now() - startTime
  if (ms < 1000) return `${ms}ms`
  const secs = Math.floor(ms / 1000)
  if (secs < 60) return `${secs}s`
  const mins = Math.floor(secs / 60)
  const remSecs = secs % 60
  return `${mins}m ${remSecs}s`
}

/**
 * Parse an ISO-8601 duration (PT1H2M3.4S) into a human-readable string.
 * Returns the raw string if the pattern doesn't match.
 */
export function formatDuration(duration: string | null): string {
  if (!duration) return ''
  const match = duration.match(/PT(?:(\d+)H)?(?:(\d+)M)?(?:([\d.]+)S)?/)
  if (!match) return duration
  const hours = Number.parseInt(match[1] ?? '0', 10)
  const mins = Number.parseInt(match[2] ?? '0', 10)
  const secs = Number.parseFloat(match[3] ?? '0')
  const parts: string[] = []
  if (hours > 0) parts.push(`${hours}h`)
  if (mins > 0) parts.push(`${mins}m`)
  parts.push(`${secs.toFixed(1)}s`)
  return parts.join(' ')
}

/**
 * Promise-based sleep.
 */
export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms)
  })
}
