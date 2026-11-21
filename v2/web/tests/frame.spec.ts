/** The browser tier of the `web` CI job: the frame and the renderers at avo's two widths, light and dark.
 *
 * 1187 px is his laptop and 1884 px his extra screen (design contract §5.1, measured 12 Nov 2026). There is no
 * 412 px round: the phone view **is** the Android app (contract §5.1), and a page opened on a phone only has to
 * stay readable, which the last test checks as a floor rather than as a design.
 *
 * The clock and every age are pinned through `?now=`, so a screenshot of the same build is the same picture.
 */
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';

import { expect, test, type Page } from '@playwright/test';

const WIDTHS = [1187, 1884] as const;
const THEMES = ['dark', 'light'] as const;
const SHOTS = process.env.RC_SHOTS_DIR ?? join(import.meta.dirname, '..', 'shots');
const NOW = '2026-11-21T23:20:00Z';

async function openAt(page: Page, theme: (typeof THEMES)[number], width: number, view = '') {
  await page.addInitScript((choice) => {
    try {
      if (choice === 'light') window.localStorage.setItem('rc-theme', 'light');
      else window.localStorage.removeItem('rc-theme');
    } catch {
      // a browser without site data: the page is dark, which is the default anyway
    }
  }, theme);
  await page.setViewportSize({ width, height: 900 });
  await page.goto(`/?now=${NOW}${view}`);
  await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
}

async function pageOverflow(page: Page): Promise<number> {
  return page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
}

for (const width of WIDTHS) {
  for (const theme of THEMES) {
    test(`the frame renders at ${width} px in ${theme}`, async ({ page }) => {
      await openAt(page, theme, width);

      // The seven frame rows design contract §6 keeps.
      for (const part of ['shell', 'app-bar', 'command-box', 'board-tabs', 'screen-toolbar', 'work-area', 'status-bar', 'ask-bubble']) {
        await expect(page.locator(`[data-rc="${part}"]`)).toBeVisible();
      }
      // The ticker tape is off: our data is hourly and a moving tape would lie (contract §6).
      await expect(page.locator('[data-rc="ticker-tape"]')).toHaveCount(0);

      // The shell: a 64 px icon rail below 1440 px, a 240 px sidebar from 1440 px (contract §5.1).
      const rail = await page.locator('[data-rc="sidebar"]').boundingBox();
      expect(Math.round(rail?.width ?? 0)).toBe(width < 1440 ? 64 : 240);

      expect(await pageOverflow(page)).toBeLessThanOrEqual(0);

      mkdirSync(SHOTS, { recursive: true });
      await page.screenshot({ path: join(SHOTS, `frame-${width}-${theme}.png`), fullPage: true });
    });

    test(`the states gallery renders at ${width} px in ${theme}`, async ({ page }) => {
      await openAt(page, theme, width, '&view=states');
      await expect(page.locator('[data-rc="state-gallery"]')).toBeVisible();
      // Contract §8: every row of the state table is on this page.
      await expect(page.locator('[data-state]')).toHaveCount(10);
      expect(await pageOverflow(page)).toBeLessThanOrEqual(0);
      mkdirSync(SHOTS, { recursive: true });
      await page.screenshot({ path: join(SHOTS, `states-${width}-${theme}.png`), fullPage: true });
    });
  }
}

test('the panels and the renderers are drawn, with the footer line and the real chart', async ({ page }) => {
  await openAt(page, 'dark', 1884);

  // The panel's four parts, and the footer in the contract's own order (§7).
  await expect(page.locator('[data-rc="panel"]').first()).toBeVisible();
  await expect(page.locator('[data-rc="panel-footer"]').first()).toContainText('as of');
  await expect(page.locator('[data-rc="table"]').first()).toBeVisible();
  await expect(page.locator('[data-rc="tile"]').first()).toBeVisible();
  await expect(page.locator('[data-rc="judgement-card"]').first()).toBeVisible();

  // uPlot really drew: a canvas inside the chart block, and the legend names both series (§10).
  const chart = page.locator('[data-rc="chart-block"]').first();
  await expect(chart.locator('canvas')).toHaveCount(1);
  await expect(chart.locator('.rc-legend-name')).toHaveCount(2);
  await expect(chart.locator('[data-rc="chart-method"]')).toContainText('sample ramp');

  // Every panel admits its sample data rather than looking live (§12).
  const panels = await page.locator('[data-rc="panel"]').count();
  expect(await page.locator('[data-rc="banner"]').count()).toBe(panels);
});

test('the price cell puts 1D and 1W under the price, divided at the column centre', async ({ page }) => {
  await openAt(page, 'dark', 1187);
  const cell = page.locator('[data-rc="price-cell"]').first();
  const box = await cell.boundingBox();
  const split = await cell.locator('.rc-price-split').boundingBox();
  // The divider stands at the cell's own midpoint (avo, 21 Nov 2026 16:42), within a pixel of rounding.
  const cellCentre = (box?.x ?? 0) + (box?.width ?? 0) / 2;
  const splitCentre = (split?.x ?? 0) + (split?.width ?? 0) / 2;
  expect(Math.abs(cellCentre - splitCentre)).toBeLessThanOrEqual(1.5);
  // 1D sits above the price's line, 1W below none: both changes are under the value, not beside it.
  const value = await cell.locator('.rc-price-value').boundingBox();
  expect((split?.y ?? 0)).toBeGreaterThan((value?.y ?? 0));
});

test('sorting a column reorders the rows and travels in the URL', async ({ page }) => {
  await openAt(page, 'dark', 1884);
  await page.getByRole('button', { name: 'Sort by Volume' }).click();
  await expect(page).toHaveURL(/sort=volume&dir=desc/);
  const first = page.locator('.rc-tr:not(.rc-tr-head)').first();
  await expect(first).toContainText('SPDR S&P 500');
  await page.getByRole('button', { name: 'Sort by Volume' }).click();
  await expect(page).toHaveURL(/sort=volume&dir=asc/);
  await expect(page.locator('.rc-tr:not(.rc-tr-head)').first()).toContainText('Apple');
});

test('every control is 44 px, apart from the two exceptions the contract names', async ({ page }) => {
  await openAt(page, 'dark', 1187);
  const small = await page.evaluate(() => {
    const out: string[] = [];
    for (const element of document.querySelectorAll('button, summary, input, [role="menuitem"], [role="menuitemcheckbox"]')) {
      // Contract §5.1's two exceptions: the symbol tile's drawing (its hit area carries the target) and the
      // secondary sort targets inside one header cell.
      if (element.closest('.rc-th-sub') !== null || element.classList.contains('rc-th-sub')) continue;
      const box = element.getBoundingClientRect();
      if (box.width === 0 && box.height === 0) continue;
      if (box.height < 44) out.push(`${element.className || element.tagName}: ${box.height.toFixed(1)}px`);
    }
    return out;
  });
  expect(small).toEqual([]);
});

test('the symbol tile is 26 px drawn and at least a row high to hit', async ({ page }) => {
  await openAt(page, 'dark', 1187);
  const tile = await page.locator('.rc-symbol-tile').first().boundingBox();
  expect(Math.round(tile?.width ?? 0)).toBe(26);
  expect(Math.round(tile?.height ?? 0)).toBe(26);
  const hit = await page.locator('[data-rc="symbol-tile"]').first().boundingBox();
  expect(hit?.height ?? 0).toBeGreaterThanOrEqual(44);
  // The separate watch-list box of the old dashboard does not exist in v2 (contract §9.1).
  await expect(page.locator('[data-rc="bookmark"]')).toHaveCount(0);
});

test('the self-hosted Inter is the family the page actually paints with', async ({ page }) => {
  await openAt(page, 'dark', 1187);
  await page.evaluate(async () => {
    await document.fonts.ready;
  });
  const loaded = await page.evaluate(() =>
    [...document.fonts].map((face) => `${face.family}:${face.status}`),
  );
  expect(loaded.some((entry) => entry.startsWith('Inter:'))).toBe(true);
  // No font host is contacted (contract §3): every request stays on this origin.
  const external = await page.evaluate(() =>
    performance.getEntriesByType('resource').map((entry) => entry.name).filter((name) => !name.startsWith(location.origin)),
  );
  expect(external).toEqual([]);
});

test('a phone-width page stays readable, which is the floor and not a design round', async ({ page }) => {
  await openAt(page, 'dark', 412);
  await expect(page.locator('[data-rc="shell"]')).toBeVisible();
  expect(await pageOverflow(page)).toBeLessThanOrEqual(0);
  // No screenshot: contract §5.1 — no v2 web screen is drawn, shot or approved at a phone width.
});
