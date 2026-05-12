import os from 'node:os'
import react from '@vitejs/plugin-react'
import tsconfigPaths from 'vite-tsconfig-paths'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [tsconfigPaths(), react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./tests/setup.tsx', 'allure-vitest/setup'],
    include: ['tests/**/*.test.ts', 'tests/**/*.test.tsx'],
    exclude: ['node_modules', '.next'],
    coverage: {
      provider: 'v8',
      reportsDirectory: 'tests/artifacts/coverage-html',
      reporter: ['text', 'html', 'lcov', 'json-summary'],
      include: ['src/**/*.{ts,tsx}'],
      exclude: [
        'src/**/*.d.ts',
        'src/lib/types/**',
        'src/app/**/layout.tsx',
        'src/app/**/error.tsx',
        'src/app/favicon.ico',
        'src/app/globals.css',
      ],
    },
    reporters: [
      'default',
      [
        'allure-vitest/reporter',
        {
          resultsDir: 'tests/artifacts/allure-results',
          environmentInfo: {
            frontend: 'next-ui',
            node_version: process.version,
            os_platform: os.platform(),
            os_release: os.release(),
          },
        },
      ],
    ],
  },
})
