/** `table` and `row-card`: the dense table of contract §11, and the stacked row card the phone's counterpart is.
 *
 * The rules this file exists to hold: a table never scrolls sideways; a box is a grid of cells, and a row never
 * sizes its own cells; a missing value stays in its place and shows "—"; every rankable column is sortable, and
 * a missing value in the sorted column sinks whichever way the column points.
 */
import { useMemo, useState } from 'react';

import type { ColumnSpec, PriceCell, Row, SortDirection, Value } from '../board/envelope';
import { clampPart, compact, compareValues, isMissing, MISSING, nextSort, num, pct, price } from '../format/format';
import { PriceStack, SortableHeader, SymbolTile } from './cells';

function align(kind: ColumnSpec['kind'], index: number, last: number): 'left' | 'center' | 'right' {
  if (kind === 'text' || index === 0) return 'left';
  if (index === last) return 'right';
  return kind === 'date' ? 'center' : 'right';
}

/** The one place a cell's string is decided, so two tables of one kind cannot format a column two ways. */
export function cellText(column: ColumnSpec, value: Value | PriceCell): string {
  if (isPriceCell(value)) return price(value.price, column.symbol ?? '', column.precision);
  if (isMissing(value)) return MISSING;
  switch (column.kind) {
    case 'percent':
      return pct(value, column.precision ?? 2);
    case 'currency':
      return compact(value, column.symbol ?? '');
    case 'number':
      return num(value, column.precision ?? 0);
    case 'price':
      return num(value, column.precision ?? 2);
    default:
      return String(value);
  }
}

function isPriceCell(value: unknown): value is PriceCell {
  return typeof value === 'object' && value !== null && 'price' in value && 'd1' in value && 'w1' in value;
}

export type DataTableProps = {
  columns: readonly ColumnSpec[];
  rows: readonly Row[];
  /** The default sort; a sort already in the URL wins over it (contract §11). */
  sort?: { key: string; direction: SortDirection } | null;
  onSortChange?: (sort: { key: string; direction: SortDirection }) => void;
  /** The ticker whose watch-list sheet is open, so the row can draw the tile pressed. */
  onOpenWatchLists?: (ticker: string) => void;
  onRowClick?: (rowId: string) => void;
  /** Contract §7: Default shows 11–13 rows; Compact is the phone and the board's own switch. */
  density?: 'default' | 'compact';
  caption: string;
};

/** `table`: one grid on the parent, fixed tracks, and nothing that scrolls sideways (contract §11). */
export function DataTable({
  columns,
  rows,
  sort = null,
  onSortChange,
  onOpenWatchLists,
  onRowClick,
  density = 'default',
  caption,
}: DataTableProps) {
  const [local, setLocal] = useState<{ key: string; direction: SortDirection } | null>(sort);
  const active = onSortChange ? sort : local;

  const sorted = useMemo(() => {
    if (!active) return [...rows];
    return [...rows].sort((a, b) => {
      const av = sortValue(a, active.key);
      const bv = sortValue(b, active.key);
      return compareValues(av, bv, active.direction);
    });
  }, [rows, active]);

  function onSort(key: string) {
    const next = nextSort(active, key);
    if (onSortChange) onSortChange(next);
    else setLocal(next);
  }

  const last = columns.length - 1;
  const withSymbol = rows.some((row) => row.symbol !== undefined);
  // `minmax(0,max-content)` per column: the grid never grows past its pane, so a table narrows and its cells
  // clip rather than the page scrolling sideways (contract §11). The symbol column is the tile's fixed width.
  const tracks = `${withSymbol ? 'max-content ' : ''}${columns.map(() => 'minmax(0,max-content)').join(' ')}`;

  return (
    <div className="rc-table" data-rc="table" data-density={density}>
      <div className="rc-table-caption">{caption}</div>
      <div className="rc-table-grid" role="table" aria-label={caption} style={{ gridTemplateColumns: tracks }}>
        <div className="rc-tr rc-tr-head" role="row">
          {withSymbol && <div className="rc-th" role="columnheader" aria-label="Watch lists" />}
          {columns.map((column, index) => (
            <div className="rc-th-cell" role="columnheader" key={column.key}>
              {column.kind === 'price' && column.detailKey === undefined ? (
                <SortableHeader
                  label={column.label}
                  sortKey={`${column.key}`}
                  current={active}
                  onSort={onSort}
                  align="right"
                  extraTargets={[
                    { key: `${column.key}.d1`, label: '1D' },
                    { key: `${column.key}.w1`, label: '1W' },
                  ]}
                />
              ) : (
                <SortableHeader
                  label={column.label}
                  sortKey={column.sortable === false ? null : column.key}
                  current={active}
                  onSort={onSort}
                  align={align(column.kind, index, last)}
                />
              )}
            </div>
          ))}
        </div>
        {sorted.map((row) => (
          <div
            className="rc-tr"
            role="row"
            key={row.id}
            data-clickable={onRowClick !== undefined}
            onClick={onRowClick === undefined ? undefined : () => onRowClick(row.id)}
          >
            {withSymbol && (
              <div className="rc-td" role="cell" data-align="left">
                {row.symbol !== undefined && (
                  <SymbolTile
                    ticker={row.symbol}
                    etf={row.etf}
                    onOpen={onOpenWatchLists === undefined ? undefined : () => onOpenWatchLists(row.symbol as string)}
                  />
                )}
              </div>
            )}
            {columns.map((column, index) => {
              const raw = row.cells[column.key];
              const partial = row.partial?.includes(column.key) ?? false;
              const detail = column.detailKey === undefined ? undefined : row.cells[column.detailKey];
              const code = column.codeKey === undefined ? undefined : row.cells[column.codeKey];
              return (
                <div
                  className="rc-td"
                  role="cell"
                  key={column.key}
                  data-align={align(column.kind, index, last)}
                  data-partial={partial}
                >
                  {isPriceCell(raw) ? (
                    <PriceStack cell={raw} symbol={column.symbol ?? ''} />
                  ) : (
                    <>
                      <span className="rc-td-figure">
                        {clampPart(cellText(column, raw))}
                        {code !== undefined && !isMissing(code) && <span className="rc-td-code"> {String(code)}</span>}
                      </span>
                      {detail !== undefined && !isMissing(detail) && (
                        <span className="rc-td-detail">{String(detail)}</span>
                      )}
                    </>
                  )}
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

/** A sorted key may point inside a stacked price cell: `price.d1` is its own sort target (contract §11). */
export function sortValue(row: Row, key: string): Value {
  const [head, part] = key.split('.');
  const raw = row.cells[head];
  if (part === undefined) return isPriceCell(raw) ? raw.price : raw;
  if (isPriceCell(raw)) return part === 'd1' ? raw.d1 : part === 'w1' ? raw.w1 : raw.price;
  return isPriceCell(raw) ? raw.price : raw;
}

export type RowCardProps = {
  columns: readonly ColumnSpec[];
  row: Row;
  /** The phone's unit of a table row; the web draws it in a detail rail and in narrow panes (contract §9). */
  onOpenWatchLists?: (ticker: string) => void;
};

/** `row-card`: one table row as a card — the shape a table takes instead of scrolling sideways (contract §5.2). */
export function RowCard({ columns, row, onOpenWatchLists }: RowCardProps) {
  const [head, ...rest] = columns;
  return (
    <div className="rc-row-card" data-rc="row-card">
      <div className="rc-row-card-head">
        {row.symbol !== undefined && (
          <SymbolTile
            ticker={row.symbol}
            etf={row.etf}
            onOpen={onOpenWatchLists === undefined ? undefined : () => onOpenWatchLists(row.symbol as string)}
          />
        )}
        <span className="rc-row-card-title">{head === undefined ? row.id : cellText(head, row.cells[head.key])}</span>
      </div>
      <dl className="rc-row-card-body">
        {rest.map((column) => {
          const raw = row.cells[column.key];
          return (
            <div className="rc-row-card-line" key={column.key}>
              <dt>{column.label}</dt>
              <dd>{isPriceCell(raw) ? <PriceStack cell={raw} symbol={column.symbol ?? ''} /> : cellText(column, raw)}</dd>
            </div>
          );
        })}
      </dl>
    </div>
  );
}
