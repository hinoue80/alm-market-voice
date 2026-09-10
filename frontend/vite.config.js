import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // When deployed to GitHub Pages the app lives at /<repo-name>/
  // VITE_BASE_PATH is injected at build time by the GitHub Actions workflow.
  // Locally (npm run dev) it defaults to '/' so nothing changes.
  base: process.env.VITE_BASE_PATH ?? '/',
})
