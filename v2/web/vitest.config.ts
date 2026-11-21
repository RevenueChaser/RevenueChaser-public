import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    // The unit tier is logic and the token files; the browser tier is Playwright (ADR decision 7).
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
});
