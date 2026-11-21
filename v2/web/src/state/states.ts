/** Contract §8: the ten situations, each naming the web component that shows it.
 *
 * "A screen is not done until every row below that can happen on it is implemented." So the table is **data
 * here**, and `v2/web/src/state/states.test.ts` fails a row whose component is not exported from
 * `src/components`. That is what stops a state from being designed and never built.
 */
import type { PanelStateName } from '../board/envelope';

export type StateRow = {
  name: PanelStateName;
  /** The situation, as the contract words it. */
  situation: string;
  /** The web component of contract §8's "Web" column. */
  component: string;
  /** True where the body is still drawn under the mark — stale and partial mark the cell, not the panel. */
  marksTheCell: boolean;
};

export const STATE_ROWS: readonly StateRow[] = [
  {
    name: 'loading',
    situation: 'A table is loading',
    component: 'SkeletonRows',
    marksTheCell: false,
  },
  {
    name: 'loading-partial',
    situation: 'Part of a graph is loading',
    component: 'SkeletonRows',
    marksTheCell: false,
  },
  {
    name: 'unconfigured',
    situation: 'Nothing configured',
    component: 'NextStepCard',
    marksTheCell: false,
  },
  {
    name: 'no-data',
    situation: 'A class has no data',
    component: 'Notice',
    marksTheCell: false,
  },
  {
    name: 'sample',
    situation: 'Sample data on screen',
    component: 'Banner',
    marksTheCell: false,
  },
  {
    name: 'stale',
    situation: 'Stale or partial data',
    component: 'Banner',
    marksTheCell: true,
  },
  {
    name: 'upstream-down',
    situation: 'An upstream is down',
    component: 'Notice',
    marksTheCell: false,
  },
  {
    name: 'gated',
    situation: 'Gated by cost or a long job',
    component: 'EstimateGate',
    marksTheCell: false,
  },
  {
    name: 'unsaved',
    situation: 'An edit is unsaved',
    component: 'UnsavedDialog',
    marksTheCell: false,
  },
  {
    name: 'refused',
    situation: 'A write is refused',
    component: 'Notice',
    marksTheCell: false,
  },
];

export function stateRow(name: PanelStateName): StateRow | null {
  return STATE_ROWS.find((row) => row.name === name) ?? null;
}

/** `ready` and `stale` draw the panel body; the other eight replace it (contract §8). */
export function drawsBody(name: PanelStateName | undefined): boolean {
  return name === undefined || name === 'ready' || name === 'stale' || name === 'sample';
}
