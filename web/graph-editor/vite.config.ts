import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // Relative asset URLs: the same build works at the hosting subfolder
  // (fido.ninja/darp-editor/) and at the root of the builder service.
  base: './',
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts', 'tools/**/*.test.ts', 'server/**/*.test.ts'],
  },
})
