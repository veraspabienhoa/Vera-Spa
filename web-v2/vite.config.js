import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(() => ({
  plugins: [react()],
  // The only supported public UI is the custom root domain app.veraspa.vn.
  base: '/',
  build: {
    sourcemap: true,
    target: 'es2020',
  },
}))
