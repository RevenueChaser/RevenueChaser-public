/** Every row of design contract §8, on one page, so "a screen is not done until every row is implemented"
 * is a thing CI can see rather than a promise in a PR body.
 *
 * It is reached at `?view=states`. It is part of the app on purpose: the states are the design (§8), and a
 * gallery kept outside the build drifts from the components it claims to show. `STATE_ROWS` drives it, so a
 * row added to the contract's table shows up here as a missing panel rather than being quietly skipped.
 */
import { useState } from 'react';

import type { FooterSpec } from '../board/envelope';
import { STATE_ROWS } from '../state/states';
import { Dialog, UnsavedDialog } from '../components';
import { PanelFromSpec, type StateText } from './BoardScreen';
import { SAMPLE_BUILD, SAMPLE_LAYOUT } from './fixture';

const TEXTS: Record<string, StateText> = {
  loading: { running: 'Reading the hourly spine' },
  'loading-partial': { running: 'Two of five sections are still loading' },
  unconfigured: {
    nextStep: {
      title: 'No watch list yet',
      what: 'A watch list decides which names this board follows.',
      action: 'Create a list',
      onAction: () => undefined,
    },
  },
  'no-data': { sentence: 'Customers and suppliers are not available for this name.' },
  sample: { waitingFor: 'the first board build' },
  stale: { sentence: 'Two cells are stale; each is marked under the number.' },
  'upstream-down': {
    sentence: 'The provider did not answer inside its 2 s budget.',
    detail: 'probe: connect timeout after 2.0 s',
  },
  gated: { gate: { pricePerCall: '$0.004 per call', calls: 142, onLoad: () => undefined } },
  refused: {
    sentence: 'That write was refused.',
    detail: 'reason: the v2 door is read-only; the write classes are step 7',
  },
};

export function StateGallery({ nowMs }: { nowMs: number }) {
  const [dialog, setDialog] = useState<'unsaved' | 'plain' | null>(null);
  const footer: FooterSpec = { source: 'sample', asof: null, nowMs, build: SAMPLE_BUILD };
  const table = SAMPLE_LAYOUT.panels[0];
  const stale = {
    ...table,
    body:
      table.body.kind === 'table'
        ? { ...table.body, rows: table.body.rows.map((row) => ({ ...row, partial: ['quote', 'volume'] })) }
        : table.body,
  };

  return (
    <div className="rc-gallery" data-rc="state-gallery">
      <h1 className="rc-gallery-title">States — design contract §8</h1>
      <p className="rc-gallery-note">
        Every row of the contract's state table, with the component it names. Sample figures throughout.
      </p>
      <div className="rc-gallery-grid">
        {STATE_ROWS.map((row) => (
          <div className="rc-gallery-cell" key={row.name} data-state={row.name}>
            <p className="rc-gallery-label">
              {row.situation} → <code>{row.component}</code>
            </p>
            {row.name === 'unsaved' ? (
              <button type="button" className="rc-button" onClick={() => setDialog('unsaved')}>
                Open the unsaved dialog
              </button>
            ) : (
              <PanelFromSpec
                spec={{ ...(row.name === 'stale' ? stale : table), state: row.name, id: `${table.id}-${row.name}` }}
                footer={footer}
                dataAsof={null}
                text={TEXTS[row.name] ?? {}}
              />
            )}
          </div>
        ))}
      </div>
      <div className="rc-gallery-cell">
        <p className="rc-gallery-label">
          A plain dialog → <code>Dialog</code>
        </p>
        <button type="button" className="rc-button" onClick={() => setDialog('plain')}>
          Open a dialog
        </button>
      </div>
      {dialog === 'unsaved' && (
        <UnsavedDialog
          unsaved={['Quotes panel: column order', 'Figures panel: period']}
          onDiscard={() => setDialog(null)}
          onCancel={() => setDialog(null)}
        />
      )}
      {dialog === 'plain' && (
        <Dialog
          title="A dialog"
          onDismiss={() => setDialog(null)}
          actions={
            <button type="button" className="rc-button" data-variant="primary" onClick={() => setDialog(null)}>
              Close
            </button>
          }
        >
          <p className="rc-dialog-text">`--r-lg` and `--elev-2`, as contract §4 sets out.</p>
        </Dialog>
      )}
    </div>
  );
}
