/** How a board's `layout` becomes panels: the generic renderers, driven by data and nothing else.
 *
 * This file adds no design component — it composes the ones design contract §9 names. A board ships a `Layout`
 * (`src/board/envelope.ts`) and never a React element, which is what "generic renderer" means here: the board
 * says what to draw, this decides how, and the same payload draws on the phone through §9's counterparts.
 */
import type { FooterSpec, PanelSpec, PanelStateName, SortDirection } from '../board/envelope';
import { drawsBody } from '../state/states';
import {
  Banner,
  ChartBlock,
  DataTable,
  EstimateGate,
  JudgementCard,
  NextStepCard,
  Notice,
  Panel,
  SkeletonRows,
  Tile,
} from '../components';

/** The words each state shows. Contract §8 fixes the shape; the sentence belongs to the panel's own subject. */
export type StateText = {
  /** What is running, for a loading panel's strip. */
  running?: string;
  /** The sentence a `no-data`, `upstream-down` or `refused` panel prints. */
  sentence?: string;
  /** The probe result or the refusal's reason. */
  detail?: string;
  /** What a sample banner is waiting for. */
  waitingFor?: string;
  /** The next step of an unconfigured panel. */
  nextStep?: { title: string; what: string; action: string; onAction: () => void };
  /** The price per call of a gated panel. */
  gate?: { pricePerCall: string; calls?: number; onLoad: () => void };
};

export type PanelFromSpecProps = {
  spec: PanelSpec;
  /** The board's footer; the panel's own `footer` overrides any part of it (contract §7). */
  footer: FooterSpec;
  dataAsof: string | null;
  text?: StateText;
  sort?: { key: string; direction: SortDirection } | null;
  onSortChange?: (sort: { key: string; direction: SortDirection }) => void;
  onSegment?: (option: string) => void;
  onOpenWatchLists?: (ticker: string) => void;
  subsetNote?: string;
  density?: 'default' | 'compact';
};

/** The widths a skeleton uses, taken from the real columns so the shape is the table's own (contract §8). */
function skeletonWidths(spec: PanelSpec): string[] {
  if (spec.body.kind === 'table') return spec.body.columns.map((_, index) => (index === 0 ? '18%' : '12%'));
  if (spec.body.kind === 'tiles') return spec.body.tiles.map(() => '22%');
  return ['100%'];
}

function stateBody(state: PanelStateName, spec: PanelSpec, text: StateText) {
  switch (state) {
    case 'loading':
    case 'loading-partial':
      return <SkeletonRows widths={skeletonWidths(spec)} running={text.running ?? 'Loading'} />;
    case 'unconfigured':
      return text.nextStep === undefined ? (
        <Notice>Nothing is configured here yet.</Notice>
      ) : (
        <NextStepCard {...text.nextStep} />
      );
    case 'no-data':
      return <Notice>{text.sentence ?? 'This class has no data for that name.'}</Notice>;
    case 'upstream-down':
      return (
        <Notice tone="neg" detail={text.detail}>
          {text.sentence ?? 'The upstream did not answer inside its 2 s budget.'}
        </Notice>
      );
    case 'refused':
      return (
        <Notice tone="neg" detail={text.detail}>
          {text.sentence ?? 'That write was refused.'}
        </Notice>
      );
    case 'gated':
      return text.gate === undefined ? (
        <Notice tone="amber">This panel is gated and has no estimate yet.</Notice>
      ) : (
        <EstimateGate description={spec.description} {...text.gate} />
      );
    default:
      return null;
  }
}

/** The banner a state puts above the body, where the body is still drawn (contract §8). */
function stateBanner(state: PanelStateName, text: StateText) {
  if (state === 'sample') {
    return <Banner waitingFor={text.waitingFor}>These are sample figures, not live data.</Banner>;
  }
  if (state === 'stale') {
    return (
      <Banner>
        {text.sentence ?? 'Some cells are stale or partial; each one is marked where the number is.'}
      </Banner>
    );
  }
  return undefined;
}

export function PanelFromSpec({
  spec,
  footer,
  dataAsof,
  text = {},
  sort = null,
  onSortChange,
  onSegment,
  onOpenWatchLists,
  subsetNote,
  density = 'default',
}: PanelFromSpecProps) {
  const state: PanelStateName = spec.state ?? 'ready';
  const merged: FooterSpec = { ...footer, ...spec.footer };
  const body = drawsBody(state) ? panelBody(spec, { sort, onSortChange, onOpenWatchLists, dataAsof, density }) : stateBody(state, spec, text);

  return (
    <Panel
      title={spec.title}
      scope={spec.scope}
      tone={spec.tone}
      count={spec.body.kind === 'table' ? spec.body.rows.length : undefined}
      description={spec.description}
      honestScope={spec.honestScope}
      segmented={
        spec.segmented === undefined || onSegment === undefined
          ? undefined
          : {
              options: spec.segmented.options,
              selected: spec.segmented.selected,
              onSelect: onSegment,
              label: `${spec.title} range`,
            }
      }
      footer={merged}
      banner={stateBanner(state, text)}
      subsetNote={subsetNote}
    >
      {body}
    </Panel>
  );
}

function panelBody(
  spec: PanelSpec,
  options: {
    sort: { key: string; direction: SortDirection } | null;
    onSortChange?: (sort: { key: string; direction: SortDirection }) => void;
    onOpenWatchLists?: (ticker: string) => void;
    dataAsof: string | null;
    density: 'default' | 'compact';
  },
) {
  const body = spec.body;
  switch (body.kind) {
    case 'table':
      return (
        <DataTable
          columns={body.columns}
          rows={body.rows}
          sort={options.sort ?? body.sort ?? null}
          onSortChange={options.onSortChange}
          onOpenWatchLists={options.onOpenWatchLists}
          density={options.density}
          caption={body.period === undefined ? spec.title : `${spec.title} — ${body.period}`}
        />
      );
    case 'tiles':
      return (
        <div className="rc-tile-strip">
          {body.tiles.map((tile) => (
            <Tile
              key={tile.id}
              label={tile.label}
              value={tile.value}
              delta={tile.delta}
              comparison={tile.comparison}
              sparkline={tile.sparkline}
            />
          ))}
        </div>
      );
    case 'chart':
      return <ChartBlock body={body} dataAsof={options.dataAsof} label={spec.title} />;
    case 'judgement':
      return (
        <JudgementCard
          title={spec.title}
          verdict={body.verdict}
          tone={body.tone}
          metrics={body.metrics}
          rationale={body.rationale}
        />
      );
  }
}
