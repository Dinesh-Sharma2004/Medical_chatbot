import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  base:"https://github.com/Dinesh-Sharma2004/Medical_chatbot",
  plugins: [react()],
  server: {
    host: 'localhost',
    port: 5000,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000', // backend
        changeOrigin: true,
        secure: false,
      },
    },
  },
})
