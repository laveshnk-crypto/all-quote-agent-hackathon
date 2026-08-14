import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Fail loudly if 5173 is taken instead of silently hopping to 5174, 5175…
    // A hopped port means a stale dev server is still running: kill it with
    // `lsof -ti :5173 | xargs kill -9` rather than stacking another one.
    strictPort: true,
  },
})
