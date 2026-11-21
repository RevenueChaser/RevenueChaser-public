/** @vitest-environment jsdom */
import { fireEvent, render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { FooterSpec } from '../board/envelope';
import {
  ChartBlock,
  FilterBar,
  FormatPreview,
  JudgementCard,
  Legend,
  Panel,
  PanelFooter,
  SegmentedControl,
  SymbolTile,
  Tile,
  WatchListMenu,
  WidgetCatalogue,
} from './index';

const FOOTER: FooterSpec = { source: 'WRDS', asof: '2026-11-21T22:36:00Z', nowMs: Date.parse('2026-11-21T23:20:00Z'), build: 'build 1f2c9ab' };

describe('the panel: four parts, always (contract §7)', () => {
  function panel() {
    return render(
      <Panel
        title="Market indices"
        scope="United States"
        count={12}
        description="One row per index, with the level and its change."
        honestScope="From the 120 symbols in your panels — not the whole market."
        segmented={{ options: ['1D', '1W', '1M', 'YTD'], selected: '1D', onSelect: () => undefined, label: 'Range' }}
        footer={FOOTER}
      >
        <p>body</p>
      </Panel>,
    );
  }

  it('draws the header strip with the tick, the title, the scope after a dot and the count badge', () => {
    const { container } = panel();
    expect(container.querySelector('.rc-panel-tick')).toBeTruthy();
    expect(container.querySelector('.rc-panel-title')?.textContent).toBe('Market indices · United States');
    expect(container.querySelector('[data-rc="badge"]')?.textContent).toBe('12');
  });

  it('puts the segmented control under the header, exclusive, and never as a dropdown at four choices', () => {
    const { container } = panel();
    expect(container.querySelector('select')).toBeNull();
    const buttons = container.querySelectorAll('[data-rc="segmented"] button');
    expect(buttons).toHaveLength(4);
    expect([...buttons].filter((button) => button.getAttribute('aria-pressed') === 'true')).toHaveLength(1);
  });

  it('carries its one-sentence description and its honest scope in the panel menu', () => {
    const { container } = panel();
    expect(container.querySelector('.rc-panel-description')?.textContent).toBe('One row per index, with the level and its change.');
    expect(container.querySelector('.rc-panel-honest')?.textContent).toContain('not the whole market');
  });

  it('ends in the footer line, in the contract order', () => {
    const { container } = panel();
    expect(container.querySelector('[data-rc="panel-footer"]')?.textContent).toBe('WRDS · as of 23:36 · 44m ago · build 1f2c9ab');
  });

  it('puts the footer last, after the body', () => {
    const { container } = panel();
    const parts = [...(container.querySelector('[data-rc="panel"]') as HTMLElement).children].map((child) => child.className);
    expect(parts[0]).toContain('rc-panel-head');
    expect(parts[parts.length - 1]).toContain('rc-panel-footer');
  });

  it('renders the footer on its own, where a panel has a source of its own', () => {
    const { container } = render(<PanelFooter {...FOOTER} source="SEC" />);
    expect(container.textContent).toContain('SEC · as of 23:36');
  });
});

describe('the tile and the judgement card', () => {
  it('stacks caps label, big value, delta chip and comparison line', () => {
    const { container } = render(
      <Tile label="Rows" value="4" delta={{ value: -1.2, label: 'vs last' }} comparison="in this sample layout" sparkline={[1, 2, 3]} />,
    );
    expect(container.querySelector('.rc-tile-label')?.textContent).toBe('Rows');
    expect(container.querySelector('.rc-tile-value')?.textContent).toBe('4');
    expect(container.querySelector('[data-rc="delta"]')?.textContent).toContain('-1.20%');
    expect(container.querySelector('[data-rc="delta"]')?.getAttribute('data-tone')).toBe('neg');
    expect(container.querySelector('.rc-tile-comparison')?.textContent).toBe('in this sample layout');
    expect(container.querySelector('[data-rc="sparkline"]')).toBeTruthy();
  });

  it('shows no score without the rule that produced it', () => {
    const { container } = render(
      <JudgementCard
        title="Fit"
        verdict="READY"
        tone="pos"
        metrics={[{ label: 'Components', value: '39 of 39' }]}
        rationale="The yardstick is design contract §9."
      />,
    );
    expect(container.querySelector('.rc-judgement-verdict')?.textContent).toBe('READY');
    expect(container.querySelector('.rc-judgement-rationale')?.textContent).toContain('yardstick');
    expect(container.querySelector('.rc-judgement-rule')).toBeTruthy();
  });
});

describe('the chart block (contract §10)', () => {
  const twoSeries = {
    kind: 'chart' as const,
    xKind: 'value' as const,
    yLabel: 'Index',
    method: 'Both lines are a sample ramp.',
    series: [
      { name: 'First series', points: [[0, 100], [1, 104]] as Array<[number, number | null]> },
      { name: 'Second series', points: [[0, 100], [1, 99]] as Array<[number, number | null]> },
    ],
  };

  it('names every series in the legend, with its own last number', () => {
    const { container } = render(<ChartBlock body={twoSeries} dataAsof={null} label="Two series" />);
    const names = [...container.querySelectorAll('.rc-legend-name')].map((entry) => entry.textContent);
    expect(names).toEqual(['First series', 'Second series']);
    expect(container.querySelectorAll('.rc-legend-value')).toHaveLength(2);
  });

  it('uses --data-1 then --data-2, in that order', () => {
    const { container } = render(<ChartBlock body={twoSeries} dataAsof={null} label="Two series" />);
    const swatches = [...container.querySelectorAll('.rc-legend-swatch')].map((swatch) => (swatch as HTMLElement).style.background);
    expect(swatches[0]).toContain('--data-1');
    expect(swatches[1]).toContain('--data-2');
  });

  it('ends in a method line, and puts the as-of in it where the x-axis is not time', () => {
    const { container } = render(<ChartBlock body={twoSeries} dataAsof="2026-11-21T22:36:00Z" label="Two series" />);
    const method = container.querySelector('[data-rc="chart-method"]')?.textContent ?? '';
    expect(method).toContain('Both lines are a sample ramp.');
    expect(method).toContain('23:36 Amsterdam');
    expect(container.querySelector('[data-rc="chart-asof"]')).toBeNull();
  });

  it('puts the as-of rule on the chart where the x-axis is time', () => {
    const body = { ...twoSeries, xKind: 'time' as const };
    const { container } = render(<ChartBlock body={body} dataAsof="2026-11-21T22:36:00Z" label="Two series" />);
    expect(container.querySelector('[data-rc="chart-asof"]')?.textContent).toContain('23:36 Amsterdam');
  });

  it('refuses a categorical chart in words, because --c1 … --c6 are not in the token file', () => {
    const body = {
      ...twoSeries,
      series: [...twoSeries.series, { name: 'Third series', points: [[0, 1]] as Array<[number, number | null]> }],
    };
    const { container } = render(<ChartBlock body={body} dataAsof={null} label="Three series" />);
    expect(container.querySelector('[data-blocked="true"]')).toBeTruthy();
    expect(container.textContent).toContain('--c1 … --c6');
    expect(container.querySelector('.rc-legend')).toBeNull();
  });

  it('offers Fixed | Fit only where the chart has a fixed range', () => {
    const { container } = render(<ChartBlock body={twoSeries} dataAsof={null} label="Two series" />);
    expect(container.querySelector('.rc-chart-axis')).toBeNull();
    const withRange = { ...twoSeries, axis: 'fit' as const, fixedRange: [90, 130] as [number, number] };
    const fixed = render(<ChartBlock body={withRange} dataAsof={null} label="Two series" />);
    expect(fixed.container.querySelector('.rc-chart-axis')).toBeTruthy();
    expect(fixed.getByRole('button', { name: 'Fixed' })).toBeTruthy();
  });
});

describe('the symbol tile is the watch-list control (contract §9.1)', () => {
  it('is drawn at 26 px with a hit area of its own, and opens the sheet', () => {
    let opened = 0;
    const { container } = render(<SymbolTile ticker="AAPL" onOpen={() => (opened += 1)} />);
    const tile = container.querySelector('.rc-symbol-tile') as HTMLElement;
    expect(tile.style.width).toBe('26px');
    fireEvent.click(container.querySelector('[data-rc="symbol-tile"]') as HTMLElement);
    expect(opened).toBe(1);
  });

  it('falls back to the monogram where there is no mark, offline', () => {
    const { container } = render(<SymbolTile ticker="QQQ" etf />);
    expect(container.querySelector('.rc-symbol-letters')?.textContent).toBe('QQ');
    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('.rc-symbol-tile')?.getAttribute('data-etf')).toBe('true');
  });

  it('wears a corner mark when the name is already on a list', () => {
    const { container } = render(<SymbolTile ticker="AAPL" onAList />);
    expect(container.querySelector('.rc-symbol-flag')).toBeTruthy();
    expect(container.querySelector('[data-rc="symbol-tile"]')?.getAttribute('aria-pressed')).toBe('true');
  });

  it('lists the lists with a tick and a + New list row', () => {
    const { container } = render(
      <WatchListMenu
        ticker="AAPL"
        lists={[{ id: 'core', name: 'Core', holds: true }, { id: 'options', name: 'Options watch list', holds: false }]}
        onToggle={() => undefined}
        onNewList={() => undefined}
        onClose={() => undefined}
      />,
    );
    expect(container.querySelectorAll('[role="menuitemcheckbox"]')).toHaveLength(2);
    expect(container.querySelector('[aria-checked="true"]')?.textContent).toContain('Core');
    expect(container.querySelector('[data-new="true"]')?.textContent).toContain('New list');
  });
});

describe('the filter bar says in words whether a filter is on (contract §9)', () => {
  const filters = [
    { id: 'cap', label: 'Market cap', value: 'any', on: false },
    { id: 'index', label: 'Index', value: 'S&P 500', on: true },
  ];

  it('names the filters that are on', () => {
    const { container } = render(<FilterBar filters={filters} onClear={() => undefined} onOpen={() => undefined} />);
    expect(container.querySelector('[data-rc="filter-context"]')?.textContent).toBe('1 filter is on — Index S&P 500.');
  });

  it('says so plainly when none is', () => {
    const { container } = render(
      <FilterBar filters={filters.map((filter) => ({ ...filter, on: false }))} onClear={() => undefined} onOpen={() => undefined} />,
    );
    expect(container.querySelector('[data-rc="filter-context"]')?.textContent).toContain('No filter is on');
  });
});

describe('the catalogue and the format preview', () => {
  it('gives every widget card a sentence and an honest scope', () => {
    const { container } = render(
      <WidgetCatalogue
        entries={[{ id: 'quotes', name: 'Quotes', category: 'Market', description: 'One row per instrument.', honestScope: 'Hourly, not live.' }]}
        onAdd={() => undefined}
      />,
    );
    expect(container.querySelector('.rc-catalogue-description')?.textContent).toBe('One row per instrument.');
    expect(container.querySelector('.rc-catalogue-honest')?.textContent).toBe('Hourly, not live.');
  });

  it('shows the formatting rules against real strings, with the rate and its as-of', () => {
    const { container } = render(
      <FormatPreview rules={{ currency: 'USD', alsoInView: ['CAD'], precision: 2, rate: { value: 1.0842, asof: '23:36' } }} />,
    );
    // Two currencies share "$" in this view, so the code appears (contract §3).
    expect(container.textContent).toContain('US$184.24');
    expect(container.querySelector('.rc-format-rate')?.textContent).toContain('1.0842');
    expect(container.querySelector('.rc-format-rate')?.textContent).toContain('23:36');
  });

  it('names every series in a legend of its own', () => {
    const { container } = render(<Legend entries={[{ name: 'Calls', token: '--data-1', value: '12' }]} />);
    expect(container.querySelector('.rc-legend-name')?.textContent).toBe('Calls');
  });

  it('keeps a segmented control exclusive', () => {
    const { container } = render(
      <SegmentedControl label="Range" options={['1D', '1W']} selected="1W" onSelect={() => undefined} />,
    );
    expect(container.querySelector('[aria-pressed="true"]')?.textContent).toBe('1W');
  });
});
