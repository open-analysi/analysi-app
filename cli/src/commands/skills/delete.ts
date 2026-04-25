/**
 * AUTO-GENERATED — DO NOT EDIT
 * Generated from cli-config.yaml by: npm run generate
 */

import { Args, Flags } from '@oclif/core'
import { BaseCommand } from '../../base-command.js'
import { resolvePath } from '../../lib/config-loader.js'

export default class SkillsDelete extends BaseCommand {
  static override description = 'Delete a skill'

  static override examples = [
    '<%= config.bin %> skills delete <id>',
  ]

  static override args = {
    id: Args.string({
      description: 'Skill ID to delete',
      required: true,
    })
  }
  static override flags = {
    ...BaseCommand.baseFlags,
  }

  async run(): Promise<void> {
    const { args, flags } = await this.parse(SkillsDelete)
    await this.initApi()
    const resolvedPath = resolvePath('/skills/{id}', args as Record<string, string>)

    await this.apiCall('DELETE', resolvedPath)
  }
}
