import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    // The unit tier is logic, the token files and the components in jsdom; the browser tier is Playwright
    // (ADR decision 7). A component test opens with `/** @vitest-environment jsdom */`, so a pure-logic file
    // keeps the faster node environment and nothing pays for a DOM it does not use.
    environment: 'node',
    include: ['src/**/*.test.ts', 'src/**/*.test.tsx'],
    setupFiles: ['src/test-setup.ts'],
  },
});
