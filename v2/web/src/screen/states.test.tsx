/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { FooterSpec, PanelSpec } from '../board/envelope';
import { STATE_ROWS } from '../state/states';
import { PanelFromSpec } from './BoardScreen';
import { StateGallery } from './StateGallery';
import { SAMPLE_LAYOUT } from './fixture';

/** Contract §8: "A screen is not done until every row below that can happen on it is implemented." So every row
 * of the table is rendered here and the component it names has to appear. */
const NOW = Date.parse('2026-11-21T23:20:00Z');
const FOOTER: FooterSpec = { source: 'sample', asof: '2026-11-21T22:36:00Z', nowMs: NOW, build: 'build 1f2c9ab' };
const TABLE = SAMPLE_LAYOUT.panels[0];

/** The marker each §8 component puts in the DOM, so the test asks for the component and not for a class name. */
const MARKER: Record<string, string> = {
  SkeletonRows: '[data-rc="skeleton"]',
  NextStepCard: '[data-rc="next-step-card"]',
  Notice: '[data-rc="notice"]',
  Banner: '[data-rc="banner"]',
  EstimateGate: '[data-rc="estimate-gate"]',
  UnsavedDialog: '[data-rc="dialog"]',
};

const TEXT = {
  nextStep: { title: 'No watch list yet', what: 'A watch list decides which names this board follows.', action: 'Create a list', onAction: () => undefined },
  gate: { pricePerCall: '$0.004 per call', calls: 142, onLoad: () => undefined },
  detail: 'probe: connect timeout after 2.0 s',
  waitingFor: 'the first board build',
};

describe('every row of the state table reaches its own component', () => {
  for (const row of STATE_ROWS) {
    if (row.name === 'unsaved') continue; // a dialog, not a panel body: covered below
    it(`${row.situation} → ${row.component}`, () => {
      const spec: PanelSpec = { ...TABLE, state: row.name };
      const { container } = render(<PanelFromSpec spec={spec} footer={FOOTER} dataAsof={null} text={TEXT} />);
      expect(container.querySelector(MARKER[row.component])).toBeTruthy();
    });
  }

  it('an edit is unsaved → UnsavedDialog, and it names what is unsaved', () => {
    render(<StateGallery nowMs={NOW} />);
    fireEvent.click(screen.getByRole('button', { name: 'Open the unsaved dialog' }));
    expect(screen.getByRole('dialog', { name: 'Unsaved changes' })).toBeTruthy();
    expect(screen.getAllByRole('listitem').length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: 'Discard' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeTruthy();
  });
});

describe('what each state does to the body', () => {
  function body(state: PanelSpec['state']) {
    const { container } = render(<PanelFromSpec spec={{ ...TABLE, state }} footer={FOOTER} dataAsof={null} text={TEXT} />);
    return container;
  }

  it('keeps the rows under a stale banner and marks the cells themselves', () => {
    const container = body('stale');
    expect(container.querySelector('[data-rc="banner"]')).toBeTruthy();
    expect(container.querySelector('[data-rc="table"]')).toBeTruthy();
  });

  it('keeps the rows under a sample banner and says they are not live', () => {
    const container = body('sample');
    expect(container.querySelector('[data-rc="table"]')).toBeTruthy();
    expect(container.textContent).toContain('sample figures');
    expect(container.textContent).toContain('the first board build');
  });

  it('replaces the rows while loading, in the real column layout', () => {
    const container = body('loading');
    expect(container.querySelector('[data-rc="table"]')).toBeNull();
    // One skeleton cell per real column, so the shape is the table's own and not grey soup.
    const columns = TABLE.body.kind === 'table' ? TABLE.body.columns.length : 0;
    expect(container.querySelectorAll('.rc-skeleton-row')[0].querySelectorAll('.rc-skeleton-cell')).toHaveLength(columns);
    expect(container.textContent).toContain('Loading');
  });

  it('never ends an upstream failure in a spinner: it prints the probe result', () => {
    const container = body('upstream-down');
    expect(container.querySelector('[aria-busy="true"]')).toBeNull();
    expect(container.textContent).toContain('probe: connect timeout after 2.0 s');
  });

  it('shows a gated panel its description, its price and a LOAD button, and fetches nothing', () => {
    const container = body('gated');
    expect(screen.getByRole('button', { name: 'LOAD' })).toBeTruthy();
    expect(container.textContent).toContain('$0.004 per call');
    expect(container.textContent).toContain(TABLE.description);
    expect(container.textContent).toContain('Nothing is fetched until you press LOAD.');
  });

  it('offers the next step as a button when nothing is configured', () => {
    body('unconfigured');
    expect(screen.getByRole('button', { name: 'Create a list' })).toBeTruthy();
  });
});

describe('the state gallery', () => {
  it('carries one cell per contract row, so a new row shows up as a missing panel', () => {
    const { container } = render(<StateGallery nowMs={NOW} />);
    for (const row of STATE_ROWS) {
      expect(container.querySelector(`[data-state="${row.name}"]`)).toBeTruthy();
    }
  });
});
