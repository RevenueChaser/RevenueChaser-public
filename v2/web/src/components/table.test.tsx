/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { ColumnSpec, Row } from '../board/envelope';
import { DataTable, RowCard } from './index';

/** Contract §11 is the section a dense board breaks first. These are its rules, over rendered output. */
const COLUMNS: ColumnSpec[] = [
  { key: 'name', label: 'Name', kind: 'text', detailKey: 'exchange' },
  { key: 'quote', label: 'Price', kind: 'price', symbol: '$' },
  { key: 'mcap', label: 'Market cap', kind: 'currency', symbol: '$' },
  { key: 'volume', label: 'Volume', kind: 'number' },
];

const ROWS: Row[] = [
  {
    id: 'aapl',
    symbol: 'AAPL',
    cells: { name: 'Apple', exchange: 'NASDAQ', quote: { price: 184.23, d1: 0.84, w1: -1.21 }, mcap: 2.87e12, volume: 54_120_000 },
  },
  {
    id: 'spy',
    symbol: 'SPY',
    etf: true,
    cells: { name: 'SPDR S&P 500', exchange: 'NYSE ARCA', quote: { price: 551.4, d1: 0.21, w1: 0.96 }, mcap: 5.4e11, volume: 72_400_000 },
  },
  {
    id: 'isrg',
    symbol: 'ISRG',
    partial: ['volume'],
    cells: { name: 'Intuitive Surgical', exchange: 'NASDAQ', quote: { price: 398.11, d1: 1.42, w1: null }, mcap: 1.4e11, volume: null },
  },
];

function rowOrder(container: HTMLElement): string[] {
  return [...container.querySelectorAll('.rc-tr:not(.rc-tr-head)')].map(
    (row) => row.querySelector('.rc-td-figure')?.textContent?.trim() ?? '',
  );
}

describe('the data table', () => {
  it('draws one grid on the parent, so a row never sizes its own cells', () => {
    const { container } = render(<DataTable columns={COLUMNS} rows={ROWS} caption="Quotes" />);
    const grid = container.querySelector('.rc-table-grid') as HTMLElement;
    // The symbol column plus one track per column: the tracks live on the grid, not on each row.
    expect(grid.style.gridTemplateColumns.split(' ').length).toBe(COLUMNS.length + 1);
    // No row carries tracks of its own: the stylesheet gives every row `grid-template-columns: subgrid`.
    for (const row of container.querySelectorAll('.rc-tr')) {
      expect((row as HTMLElement).style.gridTemplateColumns).toBe('');
    }
  });

  it('leaves a missing value as "—" in its own place rather than dropping the row', () => {
    const { container } = render(<DataTable columns={COLUMNS} rows={ROWS} caption="Quotes" />);
    expect(container.querySelectorAll('.rc-tr:not(.rc-tr-head)')).toHaveLength(3);
    expect(screen.getAllByText('—').length).toBeGreaterThan(0);
  });

  it('marks a stale or partial cell where the number is, not only in a note elsewhere', () => {
    const { container } = render(<DataTable columns={COLUMNS} rows={ROWS} caption="Quotes" />);
    expect(container.querySelectorAll('.rc-td[data-partial="true"]')).toHaveLength(1);
  });

  it('stacks the price with 1D and 1W under it, split by one muted divider', () => {
    const { container } = render(<DataTable columns={COLUMNS} rows={ROWS} caption="Quotes" />);
    const cell = container.querySelector('[data-rc="price-cell"]') as HTMLElement;
    expect(cell.querySelector('.rc-price-value')?.textContent).toBe('$184.23');
    expect(cell.querySelector('.rc-price-d1')?.textContent).toBe('+0.84%');
    expect(cell.querySelector('.rc-price-w1')?.textContent).toBe('-1.21%');
    expect(cell.querySelectorAll('.rc-price-split')).toHaveLength(1);
    // The 1D / 1W pair carries no label on the row; the header says the names once.
    expect(cell.textContent).not.toContain('1D');
  });

  it('gives the price header its two lines and a sort target per figure', () => {
    const { container } = render(<DataTable columns={COLUMNS} rows={ROWS} caption="Quotes" />);
    expect(screen.getByRole('button', { name: 'Sort by 1D' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Sort by 1W' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Sort by Price' })).toBeTruthy();
    expect(container.querySelectorAll('[data-rc="column-sort"] .rc-th-split')).toHaveLength(1);
  });

  it('sorts descending on the first tap, reverses on the second, and sinks the missing value both ways', () => {
    const { container } = render(<DataTable columns={COLUMNS} rows={ROWS} caption="Quotes" />);
    const header = screen.getByRole('button', { name: 'Sort by Volume' });

    fireEvent.click(header);
    expect(rowOrder(container)).toEqual(['SPDR S&P 500', 'Apple', 'Intuitive Surg…']);
    expect(header.querySelector('.rc-th-caret')?.textContent).toBe('▾');

    fireEvent.click(header);
    expect(rowOrder(container)).toEqual(['Apple', 'SPDR S&P 500', 'Intuitive Surg…']);
    expect(header.querySelector('.rc-th-caret')?.textContent).toBe('▴');
  });

  it('gives a caret to the active column only', () => {
    const { container } = render(<DataTable columns={COLUMNS} rows={ROWS} caption="Quotes" />);
    fireEvent.click(screen.getByRole('button', { name: 'Sort by Volume' }));
    const carets = [...container.querySelectorAll('.rc-th-caret')].map((caret) => caret.textContent);
    expect(carets.filter((caret) => caret !== '')).toHaveLength(1);
  });

  it('sorts on a stacked figure of its own', () => {
    const { container } = render(<DataTable columns={COLUMNS} rows={ROWS} caption="Quotes" />);
    fireEvent.click(screen.getByRole('button', { name: 'Sort by 1D' }));
    expect(rowOrder(container)).toEqual(['Intuitive Surg…', 'Apple', 'SPDR S&P 500']);
  });

  it('keeps every cell in its column when the rows reorder', () => {
    const { container } = render(<DataTable columns={COLUMNS} rows={ROWS} caption="Quotes" />);
    const before = [...container.querySelectorAll('.rc-tr:not(.rc-tr-head)')][0].querySelectorAll('.rc-td').length;
    fireEvent.click(screen.getByRole('button', { name: 'Sort by Volume' }));
    const after = [...container.querySelectorAll('.rc-tr:not(.rc-tr-head)')][0].querySelectorAll('.rc-td').length;
    expect(after).toBe(before);
  });

  it('puts the watch-list control left of the ticker, as the symbol tile', () => {
    const { container } = render(<DataTable columns={COLUMNS} rows={ROWS} caption="Quotes" />);
    const first = container.querySelector('.rc-tr:not(.rc-tr-head)') as HTMLElement;
    expect(first.firstElementChild?.querySelector('[data-rc="symbol-tile"]')).toBeTruthy();
    // No separate bookmark box exists in v2 (contract §9.1).
    expect(container.querySelector('[data-rc="bookmark"]')).toBeNull();
  });

  it('draws an ETF as a pill and a share as a square', () => {
    const { container } = render(<DataTable columns={COLUMNS} rows={ROWS} caption="Quotes" />);
    expect(container.querySelectorAll('.rc-symbol-tile[data-etf="true"]')).toHaveLength(1);
    expect(container.querySelectorAll('.rc-symbol-tile[data-etf="false"]')).toHaveLength(2);
  });

  it('writes a long value as figure · detail, the detail on its own muted line', () => {
    const { container } = render(<DataTable columns={COLUMNS} rows={ROWS} caption="Quotes" />);
    expect(container.querySelector('.rc-td-detail')?.textContent).toBe('NASDAQ');
  });

  it('names the period in the caption, because one table is one period', () => {
    render(<DataTable columns={COLUMNS} rows={ROWS} caption="Quotes — 2026Q3" />);
    expect(screen.getByText('Quotes — 2026Q3')).toBeTruthy();
  });
});

describe('the row card, which is what a table becomes instead of scrolling sideways', () => {
  it('carries the first column as its title and the rest as lines', () => {
    const { container } = render(<RowCard columns={COLUMNS} row={ROWS[0]} />);
    expect(container.querySelector('.rc-row-card-title')?.textContent).toBe('Apple');
    expect(container.querySelectorAll('.rc-row-card-line')).toHaveLength(COLUMNS.length - 1);
    expect(container.querySelector('[data-rc="symbol-tile"]')).toBeTruthy();
  });
});
