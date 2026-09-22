import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import layoutIdentity from './build/layoutIdentity'

export default defineConfig(() => ({
  plugins: [react({ babel: { plugins: [layoutIdentity] } })],
  // The only supported public UI is the custom root domain app.veraspa.vn.
  base: '/',
  build: {
    sourcemap: true,
    target: 'es2020',
  },
}))
