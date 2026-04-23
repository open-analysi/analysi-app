/**
 * Pack reader — load pack manifest and component files from directory or archive.
 * (Project Delos Phase 5)
 */

import { existsSync, mkdtempSync, readFileSync, readdirSync, statSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { execSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __packReaderDir = dirname(__filename)

export interface PackManifest {
  name: string
  version: string
  description: string
  type: 'built-in' | 'external'
  depends_on?: string[]
}

export interface PackContents {
  manifest: PackManifest
  dir: string
  tasks: string[]       // JSON file paths
  skills: string[]      // skill directory paths
  knowledgeUnits: string[]  // JSON file paths
  workflows: string[]   // JSON file paths
  kdgEdges: string | null   // edges.json path
  controlEventRules: string[]  // JSON file paths
}

/**
 * Resolve a pack name or path to a directory.
 * - If name matches a built-in pack under content/, use that directory
 * - If path ends with .tgz or .zip, extract to temp dir
 * - Otherwise treat as directory path
 */
export function resolvePackPath(nameOrPath: string): string {
  // Check built-in packs — try cwd first, then project root (one level up from cli/)
  const candidates = [
    resolve(process.cwd(), 'content', nameOrPath),
    resolve(__packReaderDir, '../../../content', nameOrPath),  // cli/dist/lib/ → content/
  ]
  for (const builtInDir of candidates) {
    if (existsSync(builtInDir) && statSync(builtInDir).isDirectory()) {
      return builtInDir
    }
  }

  // Check as absolute/relative path
  const absPath = resolve(nameOrPath)

  // Archive extraction
  if (nameOrPath.endsWith('.tgz') || nameOrPath.endsWith('.tar.gz')) {
    const tmpDir = mkdtempSync(join(tmpdir(), 'analysi-pack-'))
    execSync(`tar xzf "${absPath}" -C "${tmpDir}"`, { stdio: 'pipe' })
    // Find the manifest — may be in a subdirectory
    return findManifestRoot(tmpDir)
  }

  if (nameOrPath.endsWith('.zip')) {
    const tmpDir = mkdtempSync(join(tmpdir(), 'analysi-pack-'))
    execSync(`unzip -q "${absPath}" -d "${tmpDir}"`, { stdio: 'pipe' })
    return findManifestRoot(tmpDir)
  }

  if (existsSync(absPath) && statSync(absPath).isDirectory()) {
    return absPath
  }

  throw new Error(`Pack not found: ${nameOrPath}`)
}

function findManifestRoot(dir: string): string {
  if (existsSync(join(dir, 'manifest.json'))) return dir
  // Check one level deep (archives often have a single root directory)
  const entries = readdirSync(dir)
  for (const entry of entries) {
    const subDir = join(dir, entry)
    if (statSync(subDir).isDirectory() && existsSync(join(subDir, 'manifest.json'))) {
      return subDir
    }
  }
  throw new Error('Pack archive does not contain manifest.json')
}

/**
 * Read a pack directory and return its manifest + discovered component files.
 */
export function readPack(packDir: string): PackContents {
  const manifestPath = join(packDir, 'manifest.json')
  if (!existsSync(manifestPath)) {
    throw new Error(`Missing manifest.json in ${packDir}`)
  }

  const manifest = JSON.parse(readFileSync(manifestPath, 'utf-8')) as PackManifest
  if (!manifest.name || !manifest.version) {
    throw new Error('manifest.json must include name and version')
  }

  return {
    manifest,
    dir: packDir,
    tasks: listJsonFiles(join(packDir, 'tasks')),
    skills: listSubdirectories(join(packDir, 'skills')),
    knowledgeUnits: listJsonFiles(join(packDir, 'knowledge_units')),
    workflows: listJsonFiles(join(packDir, 'workflows')),
    kdgEdges: findFile(join(packDir, 'knowledge_dependency_graph'), 'edges.json'),
    controlEventRules: listJsonFiles(join(packDir, 'control_event_rules')),
  }
}

function listJsonFiles(dir: string): string[] {
  if (!existsSync(dir)) return []
  return readdirSync(dir)
    .filter((f) => f.endsWith('.json'))
    .sort()
    .map((f) => join(dir, f))
}

function listSubdirectories(dir: string): string[] {
  if (!existsSync(dir)) return []
  return readdirSync(dir)
    .filter((f) => statSync(join(dir, f)).isDirectory())
    .sort()
    .map((f) => join(dir, f))
}

function findFile(dir: string, filename: string): string | null {
  const path = join(dir, filename)
  return existsSync(path) ? path : null
}

/**
 * Sort pack names so dependencies come before dependents.
 * Reads each pack's manifest to discover depends_on relationships.
 * Unknown dependencies (not in the input list) are ignored — they'll be
 * auto-installed by the install command.
 */
export function topologicalSortPacks(packNames: string[]): string[] {
  // Read manifests to get dependency info
  const deps = new Map<string, string[]>()
  for (const name of packNames) {
    try {
      const dir = resolvePackPath(name)
      const pack = readPack(dir)
      deps.set(name, pack.manifest.depends_on ?? [])
    } catch {
      deps.set(name, [])
    }
  }

  const nameSet = new Set(packNames)
  const sorted: string[] = []
  const visited = new Set<string>()

  function visit(name: string): void {
    if (visited.has(name)) return
    visited.add(name)
    // Visit dependencies that are in our input set first
    for (const dep of deps.get(name) ?? []) {
      if (nameSet.has(dep)) visit(dep)
    }
    sorted.push(name)
  }

  for (const name of packNames) visit(name)
  return sorted
}
