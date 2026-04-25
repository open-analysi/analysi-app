/**
 * Exit codes for the Analysi CLI.
 *
 * Only well-established POSIX conventions are used:
 *   0 — Success
 *   1 — General failure (any API error, network error, runtime error)
 *   2 — Usage error (bad flags, missing args, invalid input)
 *
 * Code 2 for usage errors is standard across bash, argparse, clap, and oclif.
 * We intentionally do NOT assign custom codes (3, 4, 5...) for HTTP status
 * distinctions — that's non-standard and would surprise users.
 * Use --output json for structured error details instead.
 */

export const EXIT = {
  SUCCESS: 0,
  FAILURE: 1,
  USAGE_ERROR: 2,
} as const

/**
 * Map HTTP status codes to CLI exit codes.
 * 422 (validation) maps to USAGE_ERROR; everything else is FAILURE.
 */
export function httpStatusToExitCode(statusCode: number): number {
  if (statusCode === 422) return EXIT.USAGE_ERROR
  return EXIT.FAILURE
}
