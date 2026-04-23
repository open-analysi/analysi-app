import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    include: ['test/**/*.test.ts'],
    globals: true,
    testTimeout: 10_000,
    // Force chalk to emit ANSI codes even under vitest's captured stdout.
    // Without this, color-related assertions fail in CI (non-TTY).
    env: {
      FORCE_COLOR: '1',
    },
  },
})
