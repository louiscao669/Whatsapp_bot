import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/webhook': 'http://localhost:7861',
      '/admin': 'http://localhost:7860',
      '/api': 'http://localhost:7860',
    },
  },
})
