/**
 * Hand-written pack install command (Project Delos Phase 5).
 *
 * Reads a pack directory (or archive), then calls REST APIs in dependency
 * order to install all components. Mirrors the demo-loader's
 * StaticComponentsLoader flow.
 */

import { readFileSync, existsSync, readdirSync } from 'node:fs'
import { basename, join } from 'node:path'
import { execSync } from 'node:child_process'

import { Args } from '@oclif/core'

import { BaseCommand } from '../../base-command.js'
import { type PackContents, readPack, resolvePackPath } from '../../lib/pack-reader.js'

export default class PacksInstall extends BaseCommand {
  static override description = 'Install a content pack (tasks, skills, KUs, workflows, KDG edges, rules)'

  static override examples = [
    '<%= config.bin %> packs install foundation',
    '<%= config.bin %> packs install examples',
    '<%= config.bin %> packs install ./my-pack.tgz',
  ]

  static override args = {
    pack: Args.string({
      description: 'Pack name (built-in) or path to directory/archive',
      required: true,
    }),
  }

  static override flags = {
    ...BaseCommand.baseFlags,
  }

  // Task name→ID map for cross-reference resolution
  private taskMap = new Map<string, string>()
  // Component name→ID map for KDG edge resolution (tasks + KUs)
  private componentMap = new Map<string, string>()

  /** Ensure the pack name is in the component's categories array. */
  private addPackCategory(data: Record<string, unknown>, packName: string): void {
    const cats = Array.isArray(data.categories) ? data.categories as string[] : []
    if (!cats.includes(packName)) {
      cats.push(packName)
    }
    data.categories = cats
  }

  // Tracks packs installed in this session to avoid re-installs during dependency resolution
  private installedThisSession = new Set<string>()

  async run(): Promise<void> {
    const { args } = await this.parse(PacksInstall)
    await this.initApi()
    await this.installPack(args.pack)
  }

  /**
   * Install a single pack by name or path, auto-installing dependencies first.
   * Skips packs already installed in this CLI session.
   */
  private async installPack(nameOrPath: string): Promise<void> {
    const packDir = resolvePackPath(nameOrPath)
    const pack = readPack(packDir)

    if (this.installedThisSession.has(pack.manifest.name)) return

    // Auto-install missing dependencies first
    if (pack.manifest.depends_on?.length) {
      const packsResp = await this.client.request('GET', '/packs', this.tenantId)
      const installed = new Set(
        (packsResp.data as Array<Record<string, unknown>>).map((p) => p.name as string),
      )
      for (const name of this.installedThisSession) installed.add(name)

      const missing = pack.manifest.depends_on.filter((dep) => !installed.has(dep))
      for (const dep of missing) {
        console.log(`\n  Dependency '${dep}' not installed — installing it first...`)
        await this.installPack(dep)
      }
    }

    console.log(`\nInstalling pack: ${pack.manifest.name} v${pack.manifest.version}`)
    console.log(`  Type: ${pack.manifest.type}`)

    const counts: Record<string, number> = {}

    counts.knowledge_units = await this.installKnowledgeUnits(pack)
    counts.tasks = await this.installTasks(pack)
    counts.skills = await this.installSkills(pack)
    counts.workflows = await this.installWorkflows(pack)
    counts.kdg_edges = await this.installKdgEdges(pack)
    counts.control_event_rules = await this.installControlEventRules(pack)

    this.installedThisSession.add(pack.manifest.name)

    const total = Object.values(counts).reduce((a, b) => a + b, 0)
    console.log(`\n✓ Installed ${total} components from pack '${pack.manifest.name}'`)
    for (const [type, count] of Object.entries(counts)) {
      if (count > 0) console.log(`  ${type}: ${count}`)
    }
  }

  private async installKnowledgeUnits(pack: PackContents): Promise<number> {
    if (pack.knowledgeUnits.length === 0) return 0
    console.log(`\n  Knowledge Units...`)
    let count = 0

    for (const filePath of pack.knowledgeUnits) {
      const data = JSON.parse(readFileSync(filePath, 'utf-8'))

      // KU files can contain tables, documents, indexes arrays
      for (const kuType of ['tables', 'documents', 'indexes'] as const) {
        const items = data[kuType] as unknown[]
        if (!items?.length) continue

        for (const item of items) {
          const body: Record<string, unknown> = { ...(item as Record<string, unknown>), app: pack.manifest.name }
          // Tables need content wrapped
          if (kuType === 'tables' && body.content) {
            body.content = { rows: body.content }
          }

          try {
            const resp = await this.client.request('POST', `/knowledge-units/${kuType}`, this.tenantId, { body })
            const created = resp.data as Record<string, unknown>
            if (body.name && created.id) this.componentMap.set(body.name as string, created.id as string)
            count++
            process.stdout.write('.')
          } catch (error: any) {
            if (error.statusCode === 409 || error.message?.includes('already exists')) {
              process.stdout.write('s')  // skip
            } else {
              console.error(`\n    ✗ Failed to create ${kuType} KU: ${error.message}`)
            }
          }
        }
      }
    }

    console.log(` ${count}`)
    return count
  }

  private async installTasks(pack: PackContents): Promise<number> {
    if (pack.tasks.length === 0) return 0
    console.log(`  Tasks...`)
    let count = 0

    for (const filePath of pack.tasks) {
      const taskData = JSON.parse(readFileSync(filePath, 'utf-8'))

      // Read companion .cy script if referenced
      if (taskData.script_file) {
        const scriptPath = join(pack.dir, 'tasks', taskData.script_file)
        if (existsSync(scriptPath)) {
          taskData.script = readFileSync(scriptPath, 'utf-8')
        }
        delete taskData.script_file
      }

      // Set app field and pack category
      taskData.app = pack.manifest.name
      this.addPackCategory(taskData, pack.manifest.name)

      try {
        const response = await this.client.request('POST', '/tasks', this.tenantId, { body: taskData })
        const created = response.data as Record<string, unknown>
        // Track name→ID for workflow and KDG edge resolution
        if (taskData.name && created.id) {
          this.taskMap.set(taskData.name, created.id as string)
          this.componentMap.set(taskData.name, created.id as string)
        }
        if (taskData.cy_name && created.id) this.taskMap.set(taskData.cy_name, created.id as string)
        count++
        process.stdout.write('.')
      } catch (error: any) {
        if (error.statusCode === 409 || error.message?.includes('already exists')) {
          // On conflict, still need the ID for workflow resolution
          await this.resolveExistingTaskId(taskData.cy_name || taskData.name)
          process.stdout.write('s')
        } else {
          console.error(`\n    ✗ Failed to create task '${taskData.name}': ${error.message}`)
        }
      }
    }

    console.log(` ${count}`)
    return count
  }

  private async resolveExistingTaskId(cyNameOrName: string): Promise<void> {
    if (!cyNameOrName) return
    try {
      const response = await this.client.request('GET', '/tasks', this.tenantId, {
        query: { cy_name: cyNameOrName, limit: 1 },
      })
      const tasks = response.data as Array<Record<string, unknown>>
      if (tasks.length > 0) {
        const id = tasks[0].id as string
        this.taskMap.set(cyNameOrName, id)
        // Also track in componentMap for KDG edge resolution
        if (tasks[0].name) this.componentMap.set(tasks[0].name as string, id)
      }
    } catch {
      // Best effort
    }
  }

  /**
   * Pre-resolve task names referenced in workflows but not in the current taskMap.
   * Handles cross-pack dependencies (e.g., examples workflows using foundation tasks).
   */
  private async resolveUnknownTaskNames(pack: PackContents): Promise<void> {
    // Collect all task_cy_name values from workflow nodes
    const needed = new Set<string>()
    for (const filePath of pack.workflows) {
      const wfData = JSON.parse(readFileSync(filePath, 'utf-8'))
      if (wfData.nodes) {
        for (const node of wfData.nodes) {
          if (node.task_cy_name && !this.taskMap.has(node.task_cy_name)) {
            needed.add(node.task_cy_name)
          }
        }
      }
    }

    // Resolve each missing task from the tenant
    for (const cyName of needed) {
      await this.resolveExistingTaskId(cyName)
    }
  }

  private async installSkills(pack: PackContents): Promise<number> {
    if (pack.skills.length === 0) return 0
    console.log(`  Skills...`)
    let count = 0

    for (const skillDir of pack.skills) {
      const manifestPath = join(skillDir, 'manifest.json')
      if (!existsSync(manifestPath)) continue

      const manifest = JSON.parse(readFileSync(manifestPath, 'utf-8'))

      // Zip the skill directory (excluding manifest.json) for import
      const zipPath = `/tmp/analysi-skill-${basename(skillDir)}.zip`
      try {
        execSync(`cd "${skillDir}" && zip -r "${zipPath}" . -x manifest.json`, { stdio: 'pipe' })
      } catch {
        console.error(`\n    ✗ Failed to zip skill '${basename(skillDir)}'`)
        continue
      }

      try {
        // Upload zip via multipart form
        const zipData = readFileSync(zipPath)
        const formData = new FormData()
        formData.append('file', new Blob([zipData]), `${basename(skillDir)}.zip`)

        await this.client.requestRaw(
          'POST', `/skills/import?app=${encodeURIComponent(pack.manifest.name)}`, this.tenantId, formData
        )

        count++
        process.stdout.write('.')
      } catch (error: any) {
        if (error.statusCode === 409 || error.message?.includes('already exists')) {
          process.stdout.write('s')
        } else {
          console.error(`\n    ✗ Failed to import skill '${basename(skillDir)}': ${error.message}`)
        }
      }
    }

    console.log(` ${count}`)
    return count
  }

  private async installWorkflows(pack: PackContents): Promise<number> {
    if (pack.workflows.length === 0) return 0
    console.log(`  Workflows...`)
    let count = 0

    // Pre-resolve task names not in the current pack's taskMap
    await this.resolveUnknownTaskNames(pack)

    // Fetch existing workflow names to avoid duplicates (no unique constraint on name)
    const existingNames = new Set<string>()
    try {
      let offset = 0
      const limit = 200
      while (true) {
        const resp = await this.client.request('GET', '/workflows', this.tenantId, { query: { limit, offset } })
        const wfs = resp.data as Array<Record<string, unknown>>
        for (const wf of wfs) {
          if (wf.name) existingNames.add(wf.name as string)
        }
        if (wfs.length < limit) break
        offset += limit
      }
    } catch { /* best effort */ }

    for (const filePath of pack.workflows) {
      const wfData = JSON.parse(readFileSync(filePath, 'utf-8'))
      wfData.app = pack.manifest.name

      // Skip if workflow with this name already exists
      if (existingNames.has(wfData.name)) {
        process.stdout.write('s')
        continue
      }

      // Resolve task_cy_name → task_id in workflow nodes
      if (wfData.nodes) {
        for (const node of wfData.nodes) {
          if (node.task_cy_name) {
            const taskId = this.taskMap.get(node.task_cy_name)
            if (taskId) {
              node.task_id = taskId
            } else {
              console.error(`\n    ⚠ Could not resolve task '${node.task_cy_name}' for workflow '${wfData.name}'`)
            }
            delete node.task_cy_name
          }
        }
      }

      try {
        await this.client.request('POST', '/workflows', this.tenantId, { body: wfData })
        count++
        process.stdout.write('.')
      } catch (error: any) {
        if (error.statusCode === 409 || error.message?.includes('already exists')) {
          process.stdout.write('s')
        } else {
          console.error(`\n    ✗ Failed to create workflow '${wfData.name}': ${error.message}`)
        }
      }
    }

    console.log(` ${count}`)
    return count
  }

  private async installKdgEdges(pack: PackContents): Promise<number> {
    if (!pack.kdgEdges) return 0
    console.log(`  KDG Edges...`)

    const data = JSON.parse(readFileSync(pack.kdgEdges, 'utf-8'))
    const edges = data.edges as Array<Record<string, unknown>>
    if (!edges?.length) return 0

    // componentMap is built during task and KU install. If some components
    // were skipped (409 conflict), fill gaps with a batch fetch.
    const hasGaps = edges.some(
      (e) => !this.componentMap.has(e.from as string) || !this.componentMap.has(e.to as string),
    )
    if (hasGaps) {
      await this.backfillComponentMap()
    }

    let count = 0
    for (const edge of edges) {
      const sourceId = this.componentMap.get(edge.from as string)
      const targetId = this.componentMap.get(edge.to as string)

      if (!sourceId || !targetId) {
        console.error(`\n    ⚠ Could not resolve edge: ${edge.from} → ${edge.to}`)
        continue
      }

      const body = {
        source_id: sourceId,
        target_id: targetId,
        relationship_type: edge.relationship || 'uses',
        is_required: true,
        execution_order: 0,
        metadata: edge.metadata || {},
      }

      try {
        await this.client.request('POST', '/kdg/edges', this.tenantId, { body })
        count++
        process.stdout.write('.')
      } catch (error: any) {
        if (error.statusCode === 409 || error.message?.includes('already exists')) {
          process.stdout.write('s')
        } else {
          console.error(`\n    ✗ Failed to create edge: ${error.message}`)
        }
      }
    }

    console.log(` ${count}`)
    return count
  }

  /** Fetch all tasks and KUs to fill componentMap gaps (e.g., after 409 skips). */
  private async backfillComponentMap(): Promise<void> {
    try {
      // Paginate tasks (offset-based, 500 per page)
      let offset = 0
      const limit = 200  // API max is 200 (PaginationParams le=200)
      while (true) {
        const resp = await this.client.request('GET', '/tasks', this.tenantId, { query: { limit, offset } })
        const tasks = resp.data as Array<Record<string, unknown>>
        for (const t of tasks) {
          if (t.name && t.id) this.componentMap.set(t.name as string, t.id as string)
        }
        if (tasks.length < limit) break
        offset += limit
      }
      // KU types
      for (const kuType of ['tables', 'documents', 'indexes']) {
        offset = 0
        while (true) {
          const resp = await this.client.request('GET', `/knowledge-units/${kuType}`, this.tenantId, { query: { limit, offset } })
          const kus = resp.data as Array<Record<string, unknown>>
          for (const ku of kus) {
            if (ku.name && ku.id) this.componentMap.set(ku.name as string, ku.id as string)
          }
          if (kus.length < limit) break
          offset += limit
        }
      }
    } catch (error: any) {
      // Log so auth/network failures aren't completely silent
      console.error(`\n    ⚠ Could not fetch components for edge resolution: ${error.message || error}`)
    }
  }

  private async installControlEventRules(pack: PackContents): Promise<number> {
    if (pack.controlEventRules.length === 0) return 0
    console.log(`  Control Event Rules...`)
    let count = 0

    // Fetch existing rule names to avoid duplicates (no unique constraint on name)
    const existingRuleNames = new Set<string>()
    try {
      const resp = await this.client.request('GET', '/control-event-rules', this.tenantId)
      const rules = resp.data as Array<Record<string, unknown>>
      for (const r of rules) {
        if (r.name) existingRuleNames.add(r.name as string)
      }
    } catch { /* best effort */ }

    for (const filePath of pack.controlEventRules) {
      const ruleData = JSON.parse(readFileSync(filePath, 'utf-8'))

      // Skip if rule with this name already exists
      if (ruleData.name && existingRuleNames.has(ruleData.name)) {
        process.stdout.write('s')
        continue
      }

      // Resolve target_cy_name → target_id
      if (ruleData.target_cy_name) {
        const targetId = this.taskMap.get(ruleData.target_cy_name)
        if (targetId) {
          ruleData.target_id = targetId
        } else {
          console.error(`\n    ⚠ Could not resolve target '${ruleData.target_cy_name}' for rule '${ruleData.name}'`)
          continue
        }
        delete ruleData.target_cy_name
      }

      try {
        await this.client.request('POST', '/control-event-rules', this.tenantId, { body: ruleData })
        count++
        process.stdout.write('.')
      } catch (error: any) {
        if (error.statusCode === 409 || error.message?.includes('already exists')) {
          process.stdout.write('s')
        } else {
          console.error(`\n    ✗ Failed to create rule '${ruleData.name}': ${error.message}`)
        }
      }
    }

    console.log(` ${count}`)
    return count
  }
}
