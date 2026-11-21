import { mkdirSync } from 'node:fs';
import { join } from 'node:path';

import { expect, test } from '@playwright/test';

// The two widths of the v2 plan: avo's laptop and the extra screen. 412 px comes with step 8's layout.
const WIDTHS = [1187, 1884] as const;
const THEMES = ['dark', 'light'] as const;
const SHOTS = process.env.RC_SHOTS_DIR ?? join(import.meta.dirname, '..', 'shots');

for (const width of WIDTHS) {
  for (const theme of THEMES) {
    test(`the frame renders at ${width} px in ${theme}`, async ({ page }) => {
      await page.addInitScript((choice) => {
        try {
          if (choice === 'light') window.localStorage.setItem('rc-theme', 'light');
          else window.localStorage.removeItem('rc-theme');
        } catch {
          // a browser without site data: the page is dark, which is the default anyway
        }
      }, theme);
      await page.setViewportSize({ width, height: 900 });
      await page.goto('/');

      await expect(page.locator('[data-rc="frame"]')).toBeVisible();
      await expect(page.locator('[data-rc="statusbar"]')).toBeVisible();
      // The theme is on the root element before the body paints, as the shared contract requires.
      await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
      // No horizontal page scroll at either width.
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflow).toBeLessThanOrEqual(0);

      mkdirSync(SHOTS, { recursive: true });
      await page.screenshot({ path: join(SHOTS, `frame-${width}-${theme}.png`), fullPage: true });
    });
  }
}
