/**
 * Tests for auth-manager.ts — credential storage utilities.
 *
 * Mocks node:fs to avoid touching real ~/.config/analysi/credentials.json.
 */

import { describe, expect, it, vi, beforeEach } from 'vitest'
import { homedir } from 'node:os'
import { join } from 'node:path'

// Mock node:fs so we never touch the real filesystem
vi.mock('node:fs', () => ({
  existsSync: vi.fn(),
  mkdirSync: vi.fn(),
  readFileSync: vi.fn(),
  writeFileSync: vi.fn(),
}))

import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import {
  saveCredentials,
  loadCredentials,
  clearCredentials,
  getConfigDir,
  getCredentialsPath,
} from '../../src/lib/auth-manager.js'

const EXPECTED_CONFIG_DIR = join(homedir(), '.config', 'analysi')
const EXPECTED_CREDS_FILE = join(EXPECTED_CONFIG_DIR, 'credentials.json')

const mockExistsSync = vi.mocked(existsSync)
const mockMkdirSync = vi.mocked(mkdirSync)
const mockReadFileSync = vi.mocked(readFileSync)
const mockWriteFileSync = vi.mocked(writeFileSync)

beforeEach(() => {
  vi.clearAllMocks()
})

describe('auth-manager', () => {
  describe('saveCredentials', () => {
    it('writes JSON with mode 0o600', () => {
      mockExistsSync.mockReturnValue(true)

      const creds = { api_key: 'key-123', base_url: 'https://api.example.com' }
      saveCredentials(creds)

      expect(mockWriteFileSync).toHaveBeenCalledWith(
        EXPECTED_CREDS_FILE,
        JSON.stringify(creds, null, 2),
        { mode: 0o600 },
      )
    })

    it('creates config directory when it does not exist', () => {
      mockExistsSync.mockReturnValue(false)

      saveCredentials({ api_key: 'k', base_url: 'http://localhost' })

      expect(mockMkdirSync).toHaveBeenCalledWith(EXPECTED_CONFIG_DIR, { recursive: true })
    })
  })

  describe('loadCredentials', () => {
    it('returns null when credentials file does not exist', () => {
      mockExistsSync.mockReturnValue(false)

      expect(loadCredentials()).toBeNull()
    })

    it('returns parsed credentials when file exists', () => {
      mockExistsSync.mockReturnValue(true)
      const creds = { api_key: 'key-abc', base_url: 'https://api.test', default_tenant: 't1' }
      mockReadFileSync.mockReturnValue(JSON.stringify(creds))

      const result = loadCredentials()

      expect(result).toEqual(creds)
    })

    it('returns null on corrupt JSON', () => {
      mockExistsSync.mockReturnValue(true)
      mockReadFileSync.mockReturnValue('not valid json {{{')

      expect(loadCredentials()).toBeNull()
    })
  })

  describe('clearCredentials', () => {
    it('writes empty object when file exists', () => {
      mockExistsSync.mockReturnValue(true)

      clearCredentials()

      expect(mockWriteFileSync).toHaveBeenCalledWith(
        EXPECTED_CREDS_FILE,
        '{}',
        { mode: 0o600 },
      )
    })
  })

  describe('getConfigDir / getCredentialsPath', () => {
    it('returns expected paths based on homedir', () => {
      expect(getConfigDir()).toBe(EXPECTED_CONFIG_DIR)
      expect(getCredentialsPath()).toBe(EXPECTED_CREDS_FILE)
    })
  })
})
