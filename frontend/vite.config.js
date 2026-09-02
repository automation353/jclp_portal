import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Bind all interfaces so the dev server is reachable from outside the host.
    host: '0.0.0.0',
    // Allow any Host header (server public IP, domain, etc.)
    allowedHosts: true,
    // Proxy the API through the dev server so the browser only ever talks to
    // one origin. That keeps the Django session cookie a plain same-origin
    // cookie — no CORS config, no SameSite=None, no third-party-cookie
    // blocking to work around.
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: false,
      },
    },
  },
  build: {
    // Django collects the built bundle from here.
    outDir: 'dist',
    emptyOutDir: true,
  },
})
