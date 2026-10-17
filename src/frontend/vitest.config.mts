import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'node:path';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    env: { NEXT_PUBLIC_AUTH_MODE: 'mock' },
    globals: true,
    pool: 'threads',
    maxWorkers: 4,
    testTimeout: 15000,
    setupFiles: ['./src/__tests__/setup.ts'],
    environmentOptions: { jsdom: { url: 'http://localhost:3000' } },
  },
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
});
