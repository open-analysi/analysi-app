/**
 * Platform provision command — install packs into a tenant (Project Delos Phase 6).
 *
 * Combines tenant create + pack install. With --reset, deletes and recreates first.
 */

import { Args, Command, Flags } from '@oclif/core'

import { ApiClient, ApiError } from '../../lib/api-client.js'
import { loadCredentials } from '../../lib/auth-manager.js'
import { EXIT } from '../../lib/exit-codes.js'
import { readPack, resolvePackPath, topologicalSortPacks } from '../../lib/pack-reader.js'

export default class PlatformProvision extends Command {
  static override description = 'Provision packs into a tenant (optionally resetting it first)'

  static override examples = [
    '<%= config.bin %> platform provision acme-corp --packs foundation,examples',
    '<%= config.bin %> platform provision acme-corp --packs foundation --reset',
  ]

  static override args = {
    tenant: Args.string({ description: 'Target tenant ID', required: true }),
  }

  static override flags = {
    packs: Flags.string({
      description: 'Comma-separated list of pack names to install',
      required: true,
    }),
    reset: Flags.boolean({
      description: 'Delete and recreate the tenant before provisioning',
      default: false,
    }),
  }

  async run(): Promise<void> {
    const { args, flags } = await this.parse(PlatformProvision)

    const creds = loadCredentials()
    if (!creds?.api_key) {
      this.error('Not authenticated.', { exit: EXIT.USAGE_ERROR })
    }

    const client = new ApiClient(creds)
    const packNames = flags.packs.split(',').map((p) => p.trim())

    // Reset: delete + recreate tenant
    if (flags.reset) {
      console.log(`Resetting tenant '${args.tenant}'...`)
      try {
        await client.requestPlatform('DELETE', `/tenants/${args.tenant}`, {
          query: { confirm: args.tenant },
        })
        console.log(`  Deleted`)
      } catch (error) {
        if (error instanceof ApiError && error.statusCode === 404) {
          console.log(`  (not found, creating fresh)`)
        } else {
          throw error
        }
      }

      await client.requestPlatform('POST', '/tenants', {
        body: { id: args.tenant, name: args.tenant },
      })
      console.log(`  Created`)
    }

    // Sort packs by dependency order (e.g., foundation before examples)
    const sorted = topologicalSortPacks(packNames)

    // Install each pack in dependency order
    for (const packName of sorted) {
      console.log(`\nInstalling pack '${packName}' into tenant '${args.tenant}'...`)

      try {
        // Validate pack exists before spawning subprocess
        resolvePackPath(packName)

        const { execSync } = await import('node:child_process')
        const binPath = process.argv[1] || 'analysi'

        execSync(
          `"${binPath}" packs install "${packName}" --tenant "${args.tenant}" --yes`,
          { stdio: 'inherit' },
        )
      } catch (error) {
        if (error instanceof Error) {
          console.error(`  ✗ Failed to install pack '${packName}': ${error.message}`)
        }
      }
    }

    console.log(`\n✓ Provisioning complete for tenant '${args.tenant}'`)
  }
}
