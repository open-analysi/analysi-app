/**
 * Tests for pack-reader.ts (Project Delos Phase 7).
 */

import { describe, expect, it } from 'vitest'
import { resolve } from 'node:path'
import { readPack, resolvePackPath, topologicalSortPacks } from '../../src/lib/pack-reader.js'

const CONTENT_DIR = resolve(__dirname, '../../../content')

describe('pack-reader', () => {
  describe('resolvePackPath', () => {
    it('resolves foundation pack from content/ directory', () => {
      // resolvePackPath checks process.cwd()/content/<name>
      // In tests, we use the absolute path directly
      const dir = resolve(CONTENT_DIR, 'foundation')
      const pack = readPack(dir)
      expect(pack.manifest.name).toBe('foundation')
      expect(pack.manifest.type).toBe('built-in')
    })

    it('resolves examples pack from content/ directory', () => {
      const dir = resolve(CONTENT_DIR, 'examples')
      const pack = readPack(dir)
      expect(pack.manifest.name).toBe('examples')
      expect(pack.manifest.type).toBe('built-in')
    })
  })

  describe('readPack — foundation', () => {
    const pack = readPack(resolve(CONTENT_DIR, 'foundation'))

    it('has manifest with name, version, type', () => {
      expect(pack.manifest.name).toBe('foundation')
      expect(pack.manifest.version).toBe('1.0.0')
      expect(pack.manifest.type).toBe('built-in')
    })

    it('discovers task JSON files', () => {
      expect(pack.tasks.length).toBeGreaterThan(0)
      expect(pack.tasks.every((f) => f.endsWith('.json'))).toBe(true)
    })

    it('discovers skill directories', () => {
      expect(pack.skills.length).toBeGreaterThan(0)
    })

    it('discovers knowledge unit files', () => {
      expect(pack.knowledgeUnits.length).toBeGreaterThan(0)
    })

    it('has no workflows (all moved to examples)', () => {
      expect(pack.workflows.length).toBe(0)
    })

    it('discovers KDG edges file', () => {
      expect(pack.kdgEdges).not.toBeNull()
      expect(pack.kdgEdges).toContain('edges.json')
    })

    it('discovers control event rule files', () => {
      expect(pack.controlEventRules.length).toBeGreaterThan(0)
    })
  })

  describe('topologicalSortPacks', () => {
    it('sorts dependencies before dependents', () => {
      const sorted = topologicalSortPacks(['examples', 'foundation'])
      expect(sorted).toEqual(['foundation', 'examples'])
    })

    it('preserves order when no dependencies', () => {
      const sorted = topologicalSortPacks(['foundation'])
      expect(sorted).toEqual(['foundation'])
    })

    it('handles already-correct order', () => {
      const sorted = topologicalSortPacks(['foundation', 'examples'])
      expect(sorted).toEqual(['foundation', 'examples'])
    })

    it('returns empty array for empty input', () => {
      const sorted = topologicalSortPacks([])
      expect(sorted).toEqual([])
    })

    it('handles unknown pack names gracefully', () => {
      // Unknown pack can't be resolved — should still appear in output
      const sorted = topologicalSortPacks(['nonexistent'])
      expect(sorted).toEqual(['nonexistent'])
    })

    it('examples manifest declares foundation as dependency', () => {
      const dir = resolve(CONTENT_DIR, 'examples')
      const pack = readPack(dir)
      expect(pack.manifest.depends_on).toContain('foundation')
    })

    it('foundation manifest has no dependencies', () => {
      const dir = resolve(CONTENT_DIR, 'foundation')
      const pack = readPack(dir)
      expect(pack.manifest.depends_on ?? []).toEqual([])
    })
  })

  describe('readPack — examples', () => {
    const pack = readPack(resolve(CONTENT_DIR, 'examples'))

    it('has manifest', () => {
      expect(pack.manifest.name).toBe('examples')
    })

    it('discovers example tasks (hello_world + attack-specific)', () => {
      expect(pack.tasks.length).toBeGreaterThanOrEqual(13)
    })

    it('discovers example workflows', () => {
      expect(pack.workflows.length).toBeGreaterThanOrEqual(6)
    })
  })
})
