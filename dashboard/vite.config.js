import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev server proxies the simulator backend. BOTH /api and /dsp (the mock DSP's
// own control + bid endpoints, mounted at /dsp — NOT under /api) must be
// forwarded, or the DSP Settings tab 404s in dev. Override the target when the
// backend runs on a non-default port, e.g.:
//   VITE_PROXY_TARGET=http://localhost:9999 npm run dev
// In production the FastAPI app serves the built dist/ at the same origin, so
// relative /api and /dsp work with no proxy at all.
const target = process.env.VITE_PROXY_TARGET || 'http://localhost:8090'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target, changeOrigin: true, ws: true },
      '/dsp': { target, changeOrigin: true },
    },
  },
  build: { outDir: 'dist' },
})
