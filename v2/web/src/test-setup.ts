/** Unmount what a component test rendered, so one test's DOM never leaks into the next one's queries. */
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

afterEach(() => {
  // A node-environment test has no document; cleanup is then a no-op rather than a failure.
  if (typeof document !== 'undefined') cleanup();
});
