import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // 用 127.0.0.1 而不是 localhost：Node 可能把 localhost 解析成 IPv6，
    // 而 uvicorn 默认只监听 IPv4
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
})
