import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

/** Contract §3: "Inter, self-hosted (SIL OFL-1.1), never a font host. The web's `@font-face` arrives with step 8
 * and `tokens.test.ts` fails a font rule pointing at a file that is not there." This is that check. */
const SRC = new URL('../', import.meta.url).pathname;

function cssFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true, recursive: true })
    .filter((entry) => entry.isFile() && entry.name.endsWith('.css'))
    .map((entry) => join(entry.parentPath, entry.name));
}

const files = cssFiles(SRC);
const fontFaces = files.flatMap((file) => {
  const css = readFileSync(file, 'utf8');
  return [...css.matchAll(/@font-face\s*\{([^}]*)\}/g)].map((match) => ({ file, body: match[1] }));
});

describe('the self-hosted font', () => {
  it('declares at least one @font-face, so --font-sans is not a system fallback', () => {
    expect(fontFaces.length).toBeGreaterThan(0);
  });

  it('points every url() at a file that is really there', () => {
    const missing: string[] = [];
    for (const face of fontFaces) {
      const urls = [...face.body.matchAll(/url\(\s*['"]?([^'")]+)['"]?\s*\)/g)].map((match) => match[1]);
      expect(urls.length).toBeGreaterThan(0);
      for (const url of urls) {
        if (/^(https?:|data:)/.test(url)) {
          missing.push(`${face.file}: ${url} is not self-hosted`);
          continue;
        }
        if (!existsSync(resolve(dirname(face.file), url))) missing.push(`${face.file}: ${url}`);
      }
    }
    expect(missing).toEqual([]);
  });

  it('never names a font host: the file is served from the app (contract §3)', () => {
    for (const file of files) {
      const css = readFileSync(file, 'utf8');
      expect(css).not.toMatch(/fonts\.googleapis\.com|fonts\.gstatic\.com|use\.typekit/);
    }
  });

  it('names the family --font-sans asks for, so the rule is the one that applies', () => {
    const tokens = readFileSync(join(SRC, 'theme/tokens.css'), 'utf8');
    const sans = /--font-sans\s*:\s*([^;]+);/.exec(tokens);
    expect(sans).not.toBeNull();
    const first = (sans as RegExpExecArray)[1].split(',')[0].trim().replace(/['"]/g, '');
    expect(fontFaces.some((face) => face.body.includes(`'${first}'`) || face.body.includes(`"${first}"`))).toBe(true);
  });

  it('keeps the @font-face out of tokens.css, which is a byte-faithful copy of the design system file', () => {
    expect(readFileSync(join(SRC, 'theme/tokens.css'), 'utf8')).not.toContain('@font-face');
  });
});
