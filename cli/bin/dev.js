#!/usr/bin/env node

// Dev entry point — runs from TypeScript source directly
import { execute } from '@oclif/core'

await execute({ development: true, dir: import.meta.url })
