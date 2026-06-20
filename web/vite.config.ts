import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
// 백엔드 프록시 대상은 OMS_API_TARGET 으로 오버라이드 가능(기본 :8000).
// 예: 8000 이 다른 앱에 점유됐을 때 OMS_API_TARGET=http://localhost:8010 npm run dev
const apiTarget = process.env.OMS_API_TARGET || 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
})
