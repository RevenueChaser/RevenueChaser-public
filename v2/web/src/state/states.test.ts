import { describe, expect, it } from 'vitest';

import * as components from '../components';
import { drawsBody, STATE_ROWS, stateRow } from './states';

/** Contract §8: "A screen is not done until every row below that can happen on it is implemented." The table is
 * data here, so this test walks it instead of naming the states itself. */
describe('the state table of design contract §8', () => {
  it('has the ten rows the contract lists', () => {
    expect(STATE_ROWS).toHaveLength(10);
    expect(new Set(STATE_ROWS.map((row) => row.name)).size).toBe(10);
  });

  it('names a web component that the components barrel really exports', () => {
    const exported = components as unknown as Record<string, unknown>;
    const missing = STATE_ROWS.filter((row) => typeof exported[row.component] !== 'function').map((r) => r.component);
    expect(missing).toEqual([]);
  });

  it('marks the cell rather than the panel where the contract says the body still shows', () => {
    expect(stateRow('stale')?.marksTheCell).toBe(true);
    expect(stateRow('loading')?.marksTheCell).toBe(false);
  });

  it('keeps the body for the states that only add a banner, and replaces it for the rest', () => {
    expect(drawsBody('ready')).toBe(true);
    expect(drawsBody(undefined)).toBe(true);
    expect(drawsBody('stale')).toBe(true);
    expect(drawsBody('sample')).toBe(true);
    for (const name of ['loading', 'loading-partial', 'unconfigured', 'no-data', 'upstream-down', 'gated', 'refused'] as const) {
      expect(drawsBody(name)).toBe(false);
    }
  });

  it('knows nothing about a state the contract does not list', () => {
    expect(stateRow('ready')).toBeNull();
  });
});
