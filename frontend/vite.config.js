import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'node:path'

const backendProxy = {
  '/api': {
    target: 'http://127.0.0.1:8000',
    changeOrigin: true,
  },
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: backendProxy,
  },
  preview: {
    proxy: backendProxy,
  },
  build: {
    rolldownOptions: {
      input: resolve(import.meta.dirname, 'index.html'),
    },
  },
})
