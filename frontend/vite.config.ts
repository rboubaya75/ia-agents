/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  define: {
    // Polyfill for amazon-cognito-identity-js
    global: 'globalThis',
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.{ts,tsx}'],
    // L'origine de l'API est injectée au build (V2-LLD-010 §15.1) ; les tests en
    // fournissent une valeur factice pour couvrir la construction des URL.
    env: {
      VITE_API_BASE_URL: 'https://api.test',
    },
  },
})
