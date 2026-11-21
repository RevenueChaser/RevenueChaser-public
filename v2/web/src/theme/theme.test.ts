import { describe, expect, it } from 'vitest';

import { THEME_KEY, themeOf } from './theme';

describe('themeOf', () => {
  it('reads the two stored values', () => {
    expect(themeOf('light')).toBe('light');
    expect(themeOf('auto')).toBe('auto');
  });

  it('is dark for a missing or unknown value, so a fresh browser needs no write', () => {
    for (const stored of [null, '', 'dark', 'Light', 'neon']) expect(themeOf(stored)).toBe('dark');
  });

  it('keeps the shared storage key, which the dashboard and the design system both use', () => {
    expect(THEME_KEY).toBe('rc-theme');
  });
});
