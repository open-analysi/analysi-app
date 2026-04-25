/**
 * Loads the CLI configuration from cli-config.yaml.
 */

import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import yaml from 'js-yaml'

import type { CliConfig, OperationConfig } from './types.js'

let cachedConfig: CliConfig | null = null

/**
 * Load the CLI config from cli-config.yaml at the package root.
 */
export function loadCliConfig(): CliConfig {
  if (cachedConfig) return cachedConfig

  const currentDir = dirname(fileURLToPath(import.meta.url))
  // Navigate from dist/lib/ or src/lib/ up to package root
  const configPath = join(currentDir, '..', '..', 'cli-config.yaml')

  const raw = readFileSync(configPath, 'utf-8')
  cachedConfig = yaml.load(raw) as CliConfig
  return cachedConfig
}

/**
 * Resolve path template variables (e.g., /alerts/{alert_id})
 * with actual argument values.
 */
export function resolvePath(
  pathTemplate: string,
  args: Record<string, string>,
): string {
  return pathTemplate.replace(/\{(\w+)\}/g, (_, key: string) => {
    const value = args[key]
    if (!value) {
      throw new Error(`Missing required argument: ${key}`)
    }

    return encodeURIComponent(value)
  })
}

/**
 * Get an operation config by topic and command name.
 */
export function getOperationConfig(
  topic: string,
  command: string,
): OperationConfig | undefined {
  const config = loadCliConfig()
  return config.commands[topic]?.operations[command]
}
