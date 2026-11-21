import { describe, expect, it } from 'vitest';

import parity from '../../../parity.json';
import * as components from './index';

/** The rule step 8's proof of done states: "Every renderer in the contract's component list exists, and nothing
 * outside it was added."
 *
 * It is written over **source behaviour**, not over a list kept in this file: the names come from
 * `v2/parity.json`, which `v2/tests/test_design_contract.py` already pins to the contract's §9 table. So a
 * component the contract names and the barrel does not export fails here, on any base — which is what
 * `red-on-base` needs, since a test that only read its own allowlist would pass on the base source
 * (RevenueChaser-public #1213).
 */
const WEB_NAMES = parity.components.map((component) => component.web);

describe('the component list of design contract §9', () => {
  it('reads the parity file the contract pins', () => {
    expect(parity.contract).toBe('v2/design/CONTRACT.md');
    expect(WEB_NAMES.length).toBeGreaterThanOrEqual(30);
  });

  it('exports every component the contract names', () => {
    const exported = new Set(Object.keys(components));
    expect(WEB_NAMES.filter((name) => !exported.has(name))).toEqual([]);
  });

  it('exports each of them as a function, not as a type or a constant', () => {
    const bag = components as unknown as Record<string, unknown>;
    expect(WEB_NAMES.filter((name) => typeof bag[name] !== 'function')).toEqual([]);
  });

  it('claims `built` in the parity file only where the barrel really exports it', () => {
    const exported = new Set(Object.keys(components));
    const lying = parity.components
      .filter((component) => component.web_status === 'built' && !exported.has(component.web))
      .map((component) => component.id);
    expect(lying).toEqual([]);
  });

  it('says `built` for every component this step delivered, so the file is not stale', () => {
    const planned = parity.components.filter((component) => component.web_status !== 'built').map((c) => c.id);
    expect(planned).toEqual([]);
  });

  it('leaves the Android side planned: step 18 is what flips it', () => {
    const built = parity.components.filter((component) => component.android_status === 'built');
    expect(built).toEqual([]);
  });
});
