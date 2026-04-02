import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  // 注意：vite.config.ts 运行在 Node 环境，不能读取 import.meta.env
  // 用 process.env 读取环境变量（例如 VITE_BACKEND_PORT=8001）
  server: {
    proxy: {
      '/api': {
        target: `http://127.0.0.1:${process.env.VITE_BACKEND_PORT || '8000'}`,
        changeOrigin: true,
      },
    },
  },
})

