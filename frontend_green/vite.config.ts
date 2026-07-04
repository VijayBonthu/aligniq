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
  build: {
    rollupOptions: {
      output: {
        // Split the stable React runtime into its own long-cached chunk so it survives
        // across deploys (app code changes far more often than react/react-dom/router).
        // Route-level code-splitting (React.lazy in App.tsx) handles the rest.
        manualChunks: {
          'react-vendor': ['react', 'react-dom', 'react-router-dom'],
        },
      },
    },
  },
  // Strip all console.* and debugger statements from the production bundle.
  // We don't ship client-side logging (no Sentry); dev builds keep them.
  esbuild: {
    drop: ['console', 'debugger'],
  },
})
