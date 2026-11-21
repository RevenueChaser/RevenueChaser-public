import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

const SRC = new URL('../', import.meta.url).pathname;
const tokens = readFileSync(join(SRC, 'theme/tokens.css'), 'utf8');

function cssFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true, recursive: true })
    .filter((e) => e.isFile() && e.name.endsWith('.css'))
    .map((e) => join(e.parentPath, e.name));
}

/** `ref/design-system/DESIGN.md` §1: `var(--panel, #12161e)` renders its fallback and reports nothing, so a
 * component can follow no theme at all for months. It happened once already (public#767). This is that test. */
describe('theme tokens', () => {
  const defined = new Set([...tokens.matchAll(/(--[a-z0-9-]+)\s*:/g)].map((m) => m[1]));

  it('defines the tokens, dark by default and light under data-theme', () => {
    expect(defined.size).toBeGreaterThan(50);
    expect(tokens).toContain(':root[data-theme="light"]');
    expect(tokens).toContain('prefers-color-scheme: light');
    // tokens.css is a byte-faithful copy of the design system's file (ADR decision 5): the app's @font-face
    // lives in `theme/fonts.css`, and `theme/fonts.test.ts` fails one pointing at a file that is not there.
    expect(tokens).not.toContain('@font-face');
  });

  it('names a token the file defines in every var() of every stylesheet', () => {
    // `theme/fonts.css` is the one other exception: it is @font-face rules and no var() at all, and
    // `theme/fonts.test.ts` is what checks it (every url() resolves to a file that is really there).
    const files = cssFiles(SRC).filter((f) => !f.endsWith('theme/tokens.css') && !f.endsWith('theme/fonts.css'));
    expect(files.length).toBeGreaterThan(0);
    for (const file of files) {
      const used = [...readFileSync(file, 'utf8').matchAll(/var\(\s*(--[a-z0-9-]+)/g)].map((m) => m[1]);
      expect(used.length).toBeGreaterThan(0);
      expect(used.filter((name) => !defined.has(name))).toEqual([]);
    }
  });
});
