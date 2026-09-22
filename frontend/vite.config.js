import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
export default defineConfig({
  plugins: [vue()],
  server: { port: 5173, proxy: { '/api': 'http://127.0.0.1:8900', '/preview': 'http://127.0.0.1:8900', '/preview-assets': 'http://127.0.0.1:8900' } },
  build: { outDir: 'dist' }
})
