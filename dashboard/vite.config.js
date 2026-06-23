import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev server proxies the simulator backend (default :8090). In production the
// FastAPI app serves the built dist/ at the same origin, so relative /api works.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://localhost:8090', changeOrigin: true, ws: true },
    },
  },
  build: { outDir: 'dist' },
})
