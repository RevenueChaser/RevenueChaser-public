/** The panel's four parts (contract §7), its footer line, and the panel-level bodies: tile strip and judgement. */
import type { ReactNode } from 'react';

import type { FooterSpec, Tone } from '../board/envelope';
import { footerLine } from '../format/format';
import { Badge, DeltaChip, SegmentedControl } from './primitives';
import { Sparkline } from './cells';

/** `panel-footer`: `source · as of <HH:MM Amsterdam> · <age> · <delay or build id>`, in that order (§7). */
export function PanelFooter(spec: FooterSpec) {
  return (
    <p className="rc-panel-footer" data-rc="panel-footer">
      {footerLine(spec)}
    </p>
  );
}

export type PanelProps = {
  title: string;
  /** Printed after a dot in the header strip (contract §7). */
  scope?: string;
  /** The 3 px coloured tick of the header strip. */
  tone?: Tone;
  count?: number;
  /** The one-sentence description and the honest scope, shown in the panel menu (contract §7). */
  description: string;
  honestScope: string;
  segmented?: { options: readonly string[]; selected: string; onSelect: (option: string) => void; label: string };
  footer: FooterSpec;
  onAdd?: () => void;
  children: ReactNode;
  /** A banner above the body: sample, stale or partial data (contract §8). */
  banner?: ReactNode;
  /** The sentence a board shows above a table when it draws a subset (contract §7). */
  subsetNote?: string;
};

/** `panel`: the four parts, always — header strip, optional segmented control, body, footer line (contract §7). */
export function Panel({
  title,
  scope,
  tone = 'sky',
  count,
  description,
  honestScope,
  segmented,
  footer,
  onAdd,
  children,
  banner,
  subsetNote,
}: PanelProps) {
  return (
    <section className="rc-panel" data-rc="panel" aria-label={title}>
      <header className="rc-panel-head">
        <span className="rc-panel-tick" data-tone={tone} aria-hidden="true" />
        <h2 className="rc-panel-title">
          {title}
          {scope !== undefined && <span className="rc-panel-scope"> · {scope}</span>}
        </h2>
        <span className="rc-panel-spacer" />
        {count !== undefined && <Badge tone="neutral">{count}</Badge>}
        {onAdd !== undefined && (
          <button type="button" className="rc-icon-button" onClick={onAdd} aria-label={`Add to ${title}`}>
            <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false">
              <path d="M8 3v10M3 8h10" stroke="currentColor" strokeWidth="1.4" fill="none" />
            </svg>
          </button>
        )}
        <details className="rc-panel-menu" data-rc="panel-menu">
          <summary className="rc-icon-button" aria-label={`${title} menu`}>
            <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false">
              <path d="M2.5 4.5h11M2.5 8h11M2.5 11.5h11" stroke="currentColor" strokeWidth="1.4" fill="none" />
            </svg>
          </summary>
          <div className="rc-panel-menu-body">
            <p className="rc-panel-description">{description}</p>
            <p className="rc-panel-honest">{honestScope}</p>
          </div>
        </details>
      </header>
      {segmented !== undefined && (
        <div className="rc-panel-segmented">
          <SegmentedControl {...segmented} />
        </div>
      )}
      {banner}
      {subsetNote !== undefined && <p className="rc-panel-subset">{subsetNote}</p>}
      <div className="rc-panel-body">{children}</div>
      <PanelFooter {...footer} />
    </section>
  );
}

export type TileProps = {
  label: string;
  value: string;
  delta?: { value: number; label?: string };
  /** The comparison line: a line under a figure is data, never a description (contract §5.2). */
  comparison?: string;
  sparkline?: readonly number[];
};

/** `tile`: caps label · big value · delta chip · comparison line · optional sparkline (contract §9). */
export function Tile({ label, value, delta, comparison, sparkline }: TileProps) {
  return (
    <div className="rc-tile" data-rc="tile">
      <span className="rc-tile-label">{label}</span>
      <span className="rc-tile-value">{value}</span>
      {delta !== undefined && <DeltaChip value={delta.value} label={delta.label} />}
      {comparison !== undefined && <span className="rc-tile-comparison">{comparison}</span>}
      {sparkline !== undefined && <Sparkline points={sparkline} label={`${label} trend`} />}
    </div>
  );
}

export type JudgementCardProps = {
  title: string;
  /** One big verdict word (contract §9). */
  verdict: string;
  tone: Tone;
  metrics: ReadonlyArray<{ label: string; value: string }>;
  /** The rationale names the yardstick. No score without its rule (contract §9, §12). */
  rationale: string;
};

/** `judgement-card`: coloured top rule · caps title · one verdict word · three metric lines · a rationale. */
export function JudgementCard({ title, verdict, tone, metrics, rationale }: JudgementCardProps) {
  return (
    <div className="rc-judgement" data-rc="judgement-card" data-tone={tone}>
      <span className="rc-judgement-rule" aria-hidden="true" />
      <span className="rc-judgement-title">{title}</span>
      <strong className="rc-judgement-verdict">{verdict}</strong>
      <dl className="rc-judgement-metrics">
        {metrics.map((metric) => (
          <div className="rc-judgement-metric" key={metric.label}>
            <dt>{metric.label}</dt>
            <dd>{metric.value}</dd>
          </div>
        ))}
      </dl>
      <p className="rc-judgement-rationale">{rationale}</p>
    </div>
  );
}

export type LegendProps = {
  /** The legend names every series, in words, with its own number where it has one (contract §10). */
  entries: ReadonlyArray<{ name: string; token: string; value?: string }>;
};

/** `legend`: a colour key with no names is incomplete (contract §10). */
export function Legend({ entries }: LegendProps) {
  return (
    <ul className="rc-legend" data-rc="legend">
      {entries.map((entry) => (
        <li className="rc-legend-row" key={entry.name}>
          <span className="rc-legend-swatch" style={{ background: `var(${entry.token})` }} aria-hidden="true" />
          <span className="rc-legend-name">{entry.name}</span>
          {entry.value !== undefined && <span className="rc-legend-value">{entry.value}</span>}
        </li>
      ))}
    </ul>
  );
}

export type FilterBarProps = {
  /** A context strip says **in words** whether a filter is on (contract §9). */
  filters: ReadonlyArray<{ id: string; label: string; value: string; on: boolean }>;
  onClear: () => void;
  onOpen: (id: string) => void;
};

/** `filter-bar`: the strip, plus the sentence that says what it is doing to the rows below (contract §9). */
export function FilterBar({ filters, onClear, onOpen }: FilterBarProps) {
  const on = filters.filter((filter) => filter.on);
  return (
    <div className="rc-filter-bar" data-rc="filter-bar">
      <div className="rc-filter-row">
        {filters.map((filter) => (
          <button
            type="button"
            key={filter.id}
            className="rc-filter"
            data-on={filter.on}
            onClick={() => onOpen(filter.id)}
          >
            <span className="rc-filter-label">{filter.label}</span>
            <span className="rc-filter-value">{filter.value}</span>
          </button>
        ))}
        {on.length > 0 && (
          <button type="button" className="rc-button" onClick={onClear}>
            Clear
          </button>
        )}
      </div>
      <p className="rc-filter-context" data-rc="filter-context">
        {on.length === 0
          ? 'No filter is on: every row the board holds is shown.'
          : `${on.length === 1 ? '1 filter is' : `${on.length} filters are`} on — ${on
              .map((filter) => `${filter.label} ${filter.value}`)
              .join(', ')}.`}
      </p>
    </div>
  );
}
