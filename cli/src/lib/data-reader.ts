/**
 * Data flag parser for CLI commands.
 * Supports inline JSON strings and @filepath syntax (reads JSON from a file).
 *
 * Examples:
 *   --data '{"key": "value"}'       → parses inline JSON
 *   --data @input.json              → reads and parses file contents
 */

import { readFileSync } from 'node:fs'

/**
 * Parse a --data flag value into a JavaScript object.
 * If the value starts with '@', reads the file at that path.
 * Otherwise, parses the value as a JSON string.
 */
export function parseDataFlag(value: string): unknown {
  const trimmed = value.trim()

  if (trimmed.startsWith('@')) {
    const filePath = trimmed.slice(1)
    if (!filePath) {
      throw new Error('Missing file path after @. Usage: --data @path/to/file.json')
    }

    try {
      const content = readFileSync(filePath, 'utf-8')
      return JSON.parse(content)
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === 'ENOENT') {
        throw new Error(`File not found: ${filePath}`)
      }

      if (error instanceof SyntaxError) {
        throw new Error(`Invalid JSON in ${filePath}: ${error.message}`)
      }

      throw error
    }
  }

  try {
    return JSON.parse(trimmed)
  } catch {
    throw new Error(
      `Invalid JSON: ${trimmed.slice(0, 80)}${trimmed.length > 80 ? '...' : ''}\n` +
      'Hint: use --data @file.json to read from a file',
    )
  }
}
