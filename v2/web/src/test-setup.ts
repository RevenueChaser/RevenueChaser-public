/** What the unit tier's jsdom needs before a test file is imported.
 *
 * `setupFiles` run before the test module, which matters here: uPlot calls `matchMedia` at **import** time
 * (`setPxRatio`, `uPlot.cjs.js:80`), and jsdom has none, so without this line importing anything that imports
 * the chart block throws `matchMedia is not a function` before a single test runs. The browser tier is what
 * exercises the real media query; here it only has to exist.
 */
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

if (typeof window !== 'undefined' && typeof window.matchMedia !== 'function') {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => undefined,
    removeListener: () => undefined,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

afterEach(() => {
  // A node-environment test has no document; cleanup is then a no-op rather than a failure.
  if (typeof document !== 'undefined') cleanup();
});
