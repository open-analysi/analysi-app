/**
 * AUTO-GENERATED — DO NOT EDIT
 * Generated from cli-config.yaml by: npm run generate
 */

import { Args, Flags } from '@oclif/core'
import { BaseCommand } from '../../base-command.js'
import { resolvePath } from '../../lib/config-loader.js'

export default class SkillsGet extends BaseCommand {
  static override description = 'Get skill details'

  static override examples = [
    '<%= config.bin %> skills get <id>',
    '<%= config.bin %> skills get <id> --output json',
  ]

  static override args = {
    id: Args.string({
      description: 'Skill ID',
      required: true,
    })
  }
  static override flags = {
    ...BaseCommand.baseFlags,
  }

  async run(): Promise<void> {
    const { args, flags } = await this.parse(SkillsGet)
    await this.initApi()
    const resolvedPath = resolvePath('/skills/{id}', args as Record<string, string>)

    await this.apiCall('GET', resolvedPath)
  }
}
