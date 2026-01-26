import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// 配置参考: https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom', 'react-router-dom'],
          markdown: ['react-markdown', 'remark-gfm'],
          syntax: ['react-syntax-highlighter'],
        },
      },
    },
  },
  server: {
    port: 3001,
    proxy: {
      '/api': {
        target: 'http://localhost:8188',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://localhost:8188',
        changeOrigin: true,
      },
    },
  },
})
