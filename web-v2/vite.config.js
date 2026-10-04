import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import layoutIdentity from './build/layoutIdentity'
import buildInfo from './build/buildInfo'
import retainAssets from './build/retainAssets'

export default defineConfig(() => ({
  plugins: [react({ babel: { plugins: [layoutIdentity] } }), buildInfo(), retainAssets()],
  // The only supported public UI is the custom root domain app.veraspa.vn.
  base: '/',
  build: {
    sourcemap: true,
    target: 'es2020',
  },
}))
