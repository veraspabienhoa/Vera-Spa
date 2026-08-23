import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  // GitHub Pages serves this repo at /Vera-Spa/. Local/dev stays at root.
  base: mode === 'production' ? '/Vera-Spa/' : '/',
  build: {
    sourcemap: true,
    target: 'es2020',
  },
}))
