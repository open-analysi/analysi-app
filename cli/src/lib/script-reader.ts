/**
 * Script flag parser for CLI commands.
 * Supports inline script strings and @filepath syntax for .cy files.
 *
 * Unlike data-reader (which expects JSON), this reads raw text content.
 *
 * Examples:
 *   --script 'result = "hello"'      → inline script text
 *   --script @enrich_ip.cy           → reads file contents as plain text
 */

import { readFileSync } from 'node:fs'

/**
 * Parse a --script flag value.
 * If the value starts with '@', reads the file as UTF-8 text.
 * Otherwise, returns the value as-is (inline script).
 */
export function readScriptFlag(value: string): string {
  const trimmed = value.trim()

  if (trimmed.startsWith('@')) {
    const filePath = trimmed.slice(1)
    if (!filePath) {
      throw new Error('Missing file path after @. Usage: --script @path/to/file.cy')
    }

    try {
      return readFileSync(filePath, 'utf-8')
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === 'ENOENT') {
        throw new Error(`File not found: ${filePath}`)
      }

      throw error
    }
  }

  return trimmed
}
