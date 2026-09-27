import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      // Forward all /api requests to the FastAPI backend in development.
      // VITE_API_URL overrides the baseURL at the axios level for production;
      // the proxy is only active during `vite dev` (i.e. when VITE_API_URL is unset).
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
