/** The v2 frame, drawn row by row as design contract §6 sets it out, with the generic renderers in the work area.
 *
 * What the frame does **not** have, on purpose: a ticker tape (contract §6 — our data is hourly and a moving
 * tape would lie) and a phone layout (contract §5.1 — the phone is the Android app; a page opened on one only
 * has to stay readable).
 *
 * Step 8 wires no board: the first is Settings, at step 9. So the work area draws the sample layout of
 * `screen/fixture.ts`, every panel of it carrying the contract's `sample` banner.
 */
import { useMemo, useState } from 'react';

import type { FooterSpec, SortDirection } from './board/envelope';
import { sortFromSearch, searchWithSort } from './state/url';
import {
  AppBar,
  AskBubble,
  CommandBox,
  DetailRail,
  DocumentTabs,
  FilterBar,
  FormatPreview,
  RowCard,
  ScreenToolbar,
  SettingsRail,
  Shell,
  StatusLine,
  ThemeSwitch,
  WatchListMenu,
  WidgetCatalogue,
} from './components';
import { PanelFromSpec } from './screen/BoardScreen';
import { StateGallery } from './screen/StateGallery';
import {
  SAMPLE_BOARDS,
  SAMPLE_BUILD,
  SAMPLE_LAYOUT,
  SAMPLE_WATCH_LISTS,
  SAMPLE_WIDGETS,
  SETTINGS_GROUPS,
} from './screen/fixture';

const FILTERS = [
  { id: 'cap', label: 'Market cap', value: 'any', on: false },
  { id: 'index', label: 'Index', value: 'S&P 500', on: true },
  { id: 'sector', label: 'Sector', value: 'any', on: false },
];

/** The frame's clock and ages are read once per render from a fixed value in tests, so a screenshot is stable. */
function nowFromSearch(search: string): number {
  const pinned = new URLSearchParams(search).get('now');
  if (pinned !== null) {
    const ms = Date.parse(pinned);
    if (Number.isFinite(ms)) return ms;
  }
  return Date.now();
}

export function App() {
  const search = typeof window === 'undefined' ? '' : window.location.search;
  const view = new URLSearchParams(search).get('view');
  const nowMs = useMemo(() => nowFromSearch(search), [search]);

  const [board, setBoard] = useState<string>('welcome');
  const [sort, setSort] = useState(() => sortFromSearch(search));
  const [docTabs, setDocTabs] = useState<Array<{ id: string; title: string }>>([]);
  const [activeTab, setActiveTab] = useState('');
  const [watchFor, setWatchFor] = useState<string | null>(null);
  const [lists, setLists] = useState(SAMPLE_WATCH_LISTS);
  const [detail, setDetail] = useState<string | null>(null);
  const [density, setDensity] = useState<'default' | 'compact'>('default');
  const [filters, setFilters] = useState(FILTERS);
  const [catalogue, setCatalogue] = useState(false);
  const [setting, setSetting] = useState('theme');

  if (view === 'states') return <StateGallery nowMs={nowMs} />;

  const footer: FooterSpec = {
    source: SAMPLE_LAYOUT.source,
    asof: null,
    nowMs,
    build: SAMPLE_BUILD,
  };

  function applySort(next: { key: string; direction: SortDirection }) {
    setSort(next);
    if (typeof window !== 'undefined' && typeof window.history?.replaceState === 'function') {
      window.history.replaceState(null, '', `${window.location.pathname}${searchWithSort(window.location.search, next)}`);
    }
  }

  function openTicker(ticker: string) {
    const tab = { id: ticker, title: ticker };
    setDocTabs((open) => (open.some((item) => item.id === ticker) ? open : [...open, tab]));
    setActiveTab(ticker);
  }

  const rows = SAMPLE_LAYOUT.panels.reduce(
    (total, panel) => total + (panel.body.kind === 'table' ? panel.body.rows.length : 0),
    0,
  );
  const detailRow =
    detail === null || SAMPLE_LAYOUT.panels[0].body.kind !== 'table'
      ? null
      : SAMPLE_LAYOUT.panels[0].body.rows.find((row) => row.id === detail) ?? null;

  return (
    <Shell
      boards={SAMPLE_BOARDS}
      active={board}
      onSelectBoard={setBoard}
      appBar={
        <AppBar
          command={<CommandBox boards={SAMPLE_BOARDS} onPickBoard={setBoard} onPickTicker={openTicker} />}
          freshness={{ tone: 'amber', label: 'sample' }}
          nowMs={nowMs}
          account="avo"
        />
      }
      documentTabs={
        <DocumentTabs
          tabs={docTabs}
          active={activeTab}
          onSelect={setActiveTab}
          onClose={(id) => setDocTabs((open) => open.filter((tab) => tab.id !== id))}
        />
      }
      toolbar={
        <ScreenToolbar
          name={SAMPLE_LAYOUT.title}
          state="sample"
          count={rows}
          scope={SAMPLE_LAYOUT.scope}
          disabled={['LAYOUTS', 'SAVE', 'RESET']}
          onAction={(action) => {
            if (action === 'COMPACT') setDensity((current) => (current === 'compact' ? 'default' : 'compact'));
            if (action === 'ADD') setCatalogue(true);
          }}
        />
      }
      statusBar={<StatusLine rows={rows} build={SAMPLE_BUILD} asof="sample" />}
      rail={
        <>
          {SAMPLE_LAYOUT.rail?.items.map((item) => (
            <div className="rc-rail-item" key={item.label}>
              <span className="rc-rail-label">{item.label}</span>
              <span className="rc-rail-value" data-tone={item.tone ?? 'neutral'}>
                {item.value}
              </span>
            </div>
          ))}
          <div className="rc-rail-item">
            <span className="rc-rail-label">Theme</span>
            <ThemeSwitch />
          </div>
          <div className="rc-rail-item">
            <span className="rc-rail-label">Formats</span>
            <FormatPreview rules={{ currency: 'USD', alsoInView: ['CAD'], precision: 2, rate: { value: 1.0842, asof: '23:36' } }} />
          </div>
        </>
      }
      detail={
        detailRow === null ? undefined : (
          <DetailRail title={String(detailRow.cells.name ?? detailRow.id)} onClose={() => setDetail(null)}>
            {SAMPLE_LAYOUT.panels[0].body.kind === 'table' && (
              <RowCard columns={SAMPLE_LAYOUT.panels[0].body.columns} row={detailRow} onOpenWatchLists={setWatchFor} />
            )}
          </DetailRail>
        )
      }
      askBubble={<AskBubble onOpen={() => undefined} />}
    >
      <div className="rc-filters">
        <FilterBar
          filters={filters}
          onClear={() => setFilters((current) => current.map((filter) => ({ ...filter, on: false })))}
          onOpen={(id) => setFilters((current) => current.map((filter) => (filter.id === id ? { ...filter, on: !filter.on } : filter)))}
        />
      </div>
      {SAMPLE_LAYOUT.panels.map((panel) => (
        <PanelFromSpec
          key={panel.id}
          spec={panel}
          footer={footer}
          dataAsof={null}
          density={density}
          sort={panel.body.kind === 'table' ? sort : null}
          onSortChange={applySort}
          onOpenWatchLists={setWatchFor}
          subsetNote={panel.id === 'quotes' ? SAMPLE_LAYOUT.subsetNote : undefined}
          text={{ waitingFor: 'the first board build' }}
        />
      ))}
      {watchFor !== null && (
        <div className="rc-sheet-anchor">
          <WatchListMenu
            ticker={watchFor}
            lists={lists}
            onToggle={(id) => setLists((current) => current.map((list) => (list.id === id ? { ...list, holds: !list.holds } : list)))}
            onNewList={() => undefined}
            onClose={() => setWatchFor(null)}
          />
        </div>
      )}
      {catalogue && (
        <div className="rc-panel" data-rc="catalogue-panel">
          <div className="rc-panel-body">
            <WidgetCatalogue entries={SAMPLE_WIDGETS} onAdd={() => setCatalogue(false)} />
          </div>
        </div>
      )}
      <div className="rc-settings-preview">
        <SettingsRail groups={SETTINGS_GROUPS} active={setting} onSelect={setSetting} />
      </div>
      <button type="button" className="rc-button" onClick={() => setDetail(detail === null ? 'aapl' : null)}>
        {detail === null ? 'Open the detail rail' : 'Close the detail rail'}
      </button>
    </Shell>
  );
}
