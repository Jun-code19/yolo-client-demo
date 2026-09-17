import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

const backend = 'http://127.0.0.1:8080'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api/v1': {
        target: backend,
        changeOrigin: true,
        secure: false
      },
      '/api/v2': {
        target: backend,
        changeOrigin: true,
        secure: false
      },
      '/storage': {
        target: backend,
        changeOrigin: true,
        secure: false
      },
      '/ws/detection/preview': {
        target: backend.replace('http', 'ws'),
        ws: true,
        changeOrigin: true
      },
      '/ws/rtsp/preview': {
        target: backend.replace('http', 'ws'),
        ws: true,
        changeOrigin: true
      }
    }
  },
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src')
    }
  }
})
