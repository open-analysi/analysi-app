/**
 * Shared data-sample helpers for tasks and workflows.
 *
 * Both entities store `data_samples` as JSONB with an optional envelope
 * format: `{name, input, description, expected_output}`. This module
 * provides list/resolve helpers so the pattern isn't duplicated.
 */

import chalk from 'chalk'

export interface DataSample {
  name?: string
  input?: unknown
  description?: string
  expected_output?: unknown
  [key: string]: unknown
}

interface HasDataSamples {
  name: string
  data_samples: DataSample[] | null
}

interface ListExamplesOptions {
  /** Entity type shown in messages: "task" or "workflow" */
  entityType: string
  /** CLI command prefix for the "Run with:" hint, e.g. "analysi tasks run" */
  runCommand: string
}

/**
 * Print available data samples for an entity (task or workflow).
 */
export function listExamples(
  entity: HasDataSamples,
  entityId: string,
  options: ListExamplesOptions,
): void {
  const samples = entity.data_samples

  if (!samples || samples.length === 0) {
    console.log()
    console.log(chalk.yellow(`  No data samples defined for this ${options.entityType}`))
    console.log(chalk.dim('  Use --data to provide input manually'))
    console.log()
    return
  }

  console.log()
  console.log(chalk.bold(`  ${entity.name}`))
  console.log(chalk.dim(`  ${samples.length} example${samples.length === 1 ? '' : 's'} available`))
  console.log()

  for (let i = 0; i < samples.length; i++) {
    const sample = samples[i]
    const num = chalk.cyan(`#${i + 1}`)

    if (sample.name) {
      console.log(`  ${num}  ${sample.name}`)
      if (sample.description) {
        console.log(`       ${chalk.dim(sample.description)}`)
      }

      const input = sample.input ?? sample
      const preview = JSON.stringify(input)
      if (preview.length <= 100) {
        console.log(`       ${chalk.dim(preview)}`)
      } else {
        console.log(`       ${chalk.dim(preview.slice(0, 97) + '...')}`)
      }
    } else {
      const preview = JSON.stringify(sample)
      if (preview.length <= 100) {
        console.log(`  ${num}  ${chalk.dim(preview)}`)
      } else {
        console.log(`  ${num}  ${chalk.dim(preview.slice(0, 97) + '...')}`)
      }
    }

    console.log()
  }

  console.log(chalk.dim(`  Run with: ${options.runCommand} ${entityId.slice(0, 8)}... --example 1`))
  console.log()
}

/**
 * Resolve a 1-based example index to the input data.
 * Extracts the `input` field from envelope format, or returns the raw sample.
 * Throws (via errorFn) if the index is out of range or no samples exist.
 */
export function resolveExample(
  samples: DataSample[] | null,
  exampleNum: number,
  entityType: string,
  errorFn: (msg: string) => never,
): unknown {
  if (!samples || samples.length === 0) {
    errorFn(`This ${entityType} has no data samples. Use --data to provide input manually.`)
  }

  if (exampleNum < 1 || exampleNum > samples.length) {
    errorFn(
      `Example #${exampleNum} does not exist. This ${entityType} has ${samples.length} example${samples.length === 1 ? '' : 's'}.\n` +
      '  Use --list-examples to see them.',
    )
  }

  const sample = samples[exampleNum - 1]

  if (sample.input !== undefined) {
    return sample.input
  }

  return sample
}
