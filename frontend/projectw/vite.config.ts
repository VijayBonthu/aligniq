import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss(),],
  publicDir: 'public',
  server: {
    allowedHosts: [
      '7ede-142-198-208-131.ngrok-free.app', // Allow ngrok frontend domain
      'immense-finally-giraffe.ngrok-free.app' // Optional: Allow backend domain if needed
    ],
    port: 3000,
    open: true
  }
})
