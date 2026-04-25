/**
 * Credential storage for the Analysi CLI.
 * Stores API keys and config in ~/.config/analysi/credentials.json
 */

import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { join } from 'node:path'

import type { Credentials } from './types.js'

const CONFIG_DIR = join(homedir(), '.config', 'analysi')
const CREDENTIALS_FILE = join(CONFIG_DIR, 'credentials.json')

function ensureConfigDir(): void {
  if (!existsSync(CONFIG_DIR)) {
    mkdirSync(CONFIG_DIR, { recursive: true })
  }
}

export function saveCredentials(creds: Credentials): void {
  ensureConfigDir()
  writeFileSync(CREDENTIALS_FILE, JSON.stringify(creds, null, 2), {
    mode: 0o600, // owner read/write only
  })
}

export function loadCredentials(): Credentials | null {
  if (!existsSync(CREDENTIALS_FILE)) {
    return null
  }

  try {
    const raw = readFileSync(CREDENTIALS_FILE, 'utf-8')
    return JSON.parse(raw) as Credentials
  } catch {
    return null
  }
}

export function clearCredentials(): void {
  if (existsSync(CREDENTIALS_FILE)) {
    writeFileSync(CREDENTIALS_FILE, '{}', { mode: 0o600 })
  }
}

export function getConfigDir(): string {
  return CONFIG_DIR
}

export function getCredentialsPath(): string {
  return CREDENTIALS_FILE
}
