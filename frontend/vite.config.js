import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    // Both servers on one origin. This is why the backend has no CORS config;
    // if a CORS error appears, this proxy is misconfigured.
    proxy: { '/api': 'http://localhost:8000' },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.js',
    coverage: {
      provider: 'v8',
      // Hooks and pure helpers only. Components are not tested: all state,
      // derivation and formatting lives outside them by design.
      include: ['src/hooks/**', 'src/lib/**'],
      thresholds: { lines: 90, functions: 90, branches: 90, statements: 90 },
    },
  },
})
