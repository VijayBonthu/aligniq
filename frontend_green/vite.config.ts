import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  publicDir: 'public',
  server: {
    port: 3002,
    open: true
  },
  // Strip all console.* and debugger statements from the production bundle.
  // We don't ship client-side logging (no Sentry); dev builds keep them.
  esbuild: {
    drop: ['console', 'debugger'],
  },
})
