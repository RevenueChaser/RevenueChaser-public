/** What lives inside a row: the symbol tile and its watch-list sheet, the in-row graphics, the sortable header.
 *
 * Contract §9.1 (the tile is the watch-list control), §11 (the cell grid and the sort rules).
 */
import { useState } from 'react';

import type { PriceCell, SortDirection, Tone, Value } from '../board/envelope';
import { caretFor, isMissing, pct, price as priceText, signTone } from '../format/format';
import { monogramLetters, monogramTint, TILE_PX } from './monogram';

export type SymbolTileProps = {
  ticker: string;
  /** An ETF is a pill, a share a square, so the two read apart at a glance (contract §9.1). */
  etf?: boolean;
  /** The company's own mark, served by us — never hot-linked (contract §9.1). Absent means the monogram. */
  markUrl?: string;
  /** A name already on a list wears a small mark on the corner of its tile (contract §9.1). */
  onAList?: boolean;
  /** Tapping the tile opens the watch-list sheet; the hit area is at least the row's height. */
  onOpen?: () => void;
};

/** `symbol-tile`: 26 px at every row height, and it **is** the watch-list control (contract §9.1). */
export function SymbolTile({ ticker, etf = false, markUrl, onAList = false, onOpen }: SymbolTileProps) {
  const [markFailed, setMarkFailed] = useState(false);
  const showMark = markUrl !== undefined && !markFailed;
  return (
    <button
      type="button"
      className="rc-symbol-hit"
      data-rc="symbol-tile"
      aria-label={`${ticker} — watch lists`}
      aria-pressed={onAList}
      onClick={onOpen}
    >
      <span
        className="rc-symbol-tile"
        data-etf={etf}
        data-on-list={onAList}
        style={{ width: TILE_PX, height: TILE_PX, color: `var(${monogramTint(ticker)})` }}
      >
        {showMark ? (
          <img className="rc-symbol-mark" src={markUrl} alt="" onError={() => setMarkFailed(true)} />
        ) : (
          <span className="rc-symbol-letters">{monogramLetters(ticker)}</span>
        )}
      </span>
      {onAList && <span className="rc-symbol-flag" aria-hidden="true" />}
    </button>
  );
}

export type WatchList = { id: string; name: string; holds: boolean };

export type WatchListMenuProps = {
  ticker: string;
  lists: readonly WatchList[];
  onToggle: (id: string) => void;
  onNewList: () => void;
  onClose: () => void;
};

/** `watchlist-sheet`: the lists avo owns, a tick where the name is on one, and a `+ New list` row (§9.1). */
export function WatchListMenu({ ticker, lists, onToggle, onNewList, onClose }: WatchListMenuProps) {
  return (
    <div className="rc-sheet" data-rc="watchlist-sheet" role="menu" aria-label={`Watch lists for ${ticker}`}>
      <p className="rc-sheet-title">{ticker}</p>
      {lists.map((list) => (
        <button
          type="button"
          key={list.id}
          className="rc-sheet-row"
          role="menuitemcheckbox"
          aria-checked={list.holds}
          onClick={() => onToggle(list.id)}
        >
          <span className="rc-sheet-tick" aria-hidden="true">
            {list.holds ? '✓' : ''}
          </span>
          {list.name}
        </button>
      ))}
      <button type="button" className="rc-sheet-row" data-new="true" role="menuitem" onClick={onNewList}>
        <span className="rc-sheet-tick" aria-hidden="true">
          +
        </span>
        New list
      </button>
      <button type="button" className="rc-sheet-close" onClick={onClose}>
        Close
      </button>
    </div>
  );
}

export type SortableHeaderProps = {
  label: string;
  /** Two lines where a cell stacks two figures: `Price` over `1D | 1W` (contract §3). */
  secondLine?: string;
  sortKey: string | null;
  current: { key: string; direction: SortDirection } | null;
  onSort: (key: string) => void;
  align?: 'left' | 'center' | 'right';
  /** Each figure of a stacked cell is its own sort target (contract §11). */
  extraTargets?: ReadonlyArray<{ key: string; label: string }>;
};

/** `column-sort`: the header cell is the control, and its hit area is 44 px tall (contract §11). */
export function SortableHeader({
  label,
  secondLine,
  sortKey,
  current,
  onSort,
  align = 'left',
  extraTargets = [],
}: SortableHeaderProps) {
  if (sortKey === null) {
    return (
      <div className="rc-th" data-align={align} data-rc="header-cell">
        <span className="rc-th-label">{label}</span>
        {secondLine !== undefined && <span className="rc-th-second">{secondLine}</span>}
      </div>
    );
  }
  return (
    <div className="rc-th" data-align={align} data-rc="column-sort">
      <button type="button" className="rc-th-button" onClick={() => onSort(sortKey)} aria-label={`Sort by ${label}`}>
        <span className="rc-th-label">{label}</span>
        <span className="rc-th-caret" aria-hidden="true">
          {caretFor(current, sortKey)}
        </span>
      </button>
      {extraTargets.length > 0 && (
        <span className="rc-th-second">
          {extraTargets.map((target, index) => (
            <span key={target.key}>
              {index > 0 && <span className="rc-th-split" aria-hidden="true" />}
              <button
                type="button"
                className="rc-th-sub"
                onClick={() => onSort(target.key)}
                aria-label={`Sort by ${target.label}`}
              >
                {target.label}
                <span className="rc-th-caret" aria-hidden="true">
                  {caretFor(current, target.key)}
                </span>
              </button>
            </span>
          ))}
        </span>
      )}
      {extraTargets.length === 0 && secondLine !== undefined && <span className="rc-th-second">{secondLine}</span>}
    </div>
  );
}

/** The price cell: the price, then `1D` and `1W` under it, split by the column's own centre line (contract §3). */
export function PriceStack({ cell, symbol = '' }: { cell: PriceCell; symbol?: string }) {
  return (
    <span className="rc-price" data-rc="price-cell">
      <span className="rc-price-value">{priceText(cell.price, symbol)}</span>
      <span className="rc-price-changes">
        <span className="rc-price-d1" data-tone={signTone(cell.d1)}>
          {pct(cell.d1)}
        </span>
        <span className="rc-price-split" aria-hidden="true">
          |
        </span>
        <span className="rc-price-w1" data-tone={signTone(cell.w1)}>
          {pct(cell.w1)}
        </span>
      </span>
    </span>
  );
}

export type RangeBarProps = {
  low: number;
  high: number;
  value: number | null;
  /** The two end labels, so the bar is not read against a legend elsewhere. */
  lowLabel?: string;
  highLabel?: string;
};

/** `range-bar`: an in-row graphic (contract §9). */
export function RangeBar({ low, high, value, lowLabel, highLabel }: RangeBarProps) {
  const span = high - low;
  const at = isMissing(value) || span <= 0 ? null : Math.min(100, Math.max(0, (((value as number) - low) / span) * 100));
  return (
    <span className="rc-range" data-rc="range-bar" role="img" aria-label={`${low} to ${high}, at ${value ?? 'no value'}`}>
      <span className="rc-range-low">{lowLabel ?? low}</span>
      <span className="rc-range-track">
        {at !== null && <span className="rc-range-dot" style={{ left: `${at}%` }} />}
      </span>
      <span className="rc-range-high">{highLabel ?? high}</span>
    </span>
  );
}

export type HeatCellProps = {
  value: Value;
  text: string;
  /** 0..1 — how strong the tint is. The rule behind it is printed on the screen, not left to a legend (§9). */
  intensity: number;
};

/** `heat-cell`: the colour rule is printed on the screen, not left to a legend (contract §9). */
export function HeatCell({ value, text, intensity }: HeatCellProps) {
  const tone: Tone = signTone(value) === 'neutral' ? 'neutral' : signTone(value);
  const alpha = Math.min(1, Math.max(0, intensity));
  return (
    <span className="rc-heat" data-rc="heat-cell" data-tone={tone} style={{ opacity: 0.35 + alpha * 0.65 }}>
      {text}
    </span>
  );
}

export type SparklineProps = {
  points: readonly number[];
  width?: number;
  height?: number;
  label: string;
};

/** `sparkline`: an inline SVG line, drawn from the panel's own series and nothing else (contract §10). */
export function Sparkline({ points, width = 72, height = 20, label }: SparklineProps) {
  if (points.length < 2) {
    return (
      <span className="rc-sparkline" data-rc="sparkline" data-empty="true" role="img" aria-label={`${label}: no series`}>
        —
      </span>
    );
  }
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min || 1;
  const step = width / (points.length - 1);
  const path = points
    .map((point, index) => `${index === 0 ? 'M' : 'L'}${(index * step).toFixed(1)} ${(height - ((point - min) / span) * height).toFixed(1)}`)
    .join(' ');
  const rising = points[points.length - 1] >= points[0];
  return (
    <svg
      className="rc-sparkline"
      data-rc="sparkline"
      data-tone={rising ? 'pos' : 'neg'}
      viewBox={`0 0 ${width} ${height}`}
      width={width}
      height={height}
      role="img"
      aria-label={label}
    >
      <path d={path} fill="none" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  );
}
