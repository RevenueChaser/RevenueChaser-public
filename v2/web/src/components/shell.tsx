/** The frame of contract §6, row by row: app bar, board tabs, document tabs, screen toolbar, work area,
 * status bar, and the ask bubble. The ticker tape is **off** — our data is hourly and a moving tape would lie.
 *
 * The web shell is desktop-only (contract §5.1): a 64 px icon rail below 1440 px, a 240 px sidebar from 1440 px.
 * v2 web is given no phone layout — the phone is the Android app — but a page opened on one stays readable.
 */
import { useId, useMemo, useRef, useState, type ReactNode } from 'react';

import { amsterdamTime } from '../format/format';
import { Badge } from './primitives';

export type BoardRef = { key: string; name: string; group?: string };

export type CommandBoxProps = {
  /** One entry point: a ticker **or** a board name (contract §9). */
  boards: readonly BoardRef[];
  onPickBoard: (key: string) => void;
  onPickTicker: (ticker: string) => void;
};

/** `command-box`: the app bar's one input. A ticker goes to its page, a board name opens the board. */
export function CommandBox({ boards, onPickBoard, onPickTicker }: CommandBoxProps) {
  const [text, setText] = useState('');
  const listId = useId();
  const matches = useMemo(() => {
    const needle = text.trim().toLowerCase();
    if (needle === '') return [];
    return boards.filter((board) => board.name.toLowerCase().includes(needle) || board.key.includes(needle)).slice(0, 8);
  }, [boards, text]);

  function submit() {
    const needle = text.trim();
    if (needle === '') return;
    const board = matches[0];
    if (board !== undefined) onPickBoard(board.key);
    else onPickTicker(needle.toUpperCase());
    setText('');
  }

  return (
    <div className="rc-command" data-rc="command-box">
      <svg className="rc-command-icon" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false">
        <circle cx="7" cy="7" r="4.2" fill="none" stroke="currentColor" strokeWidth="1.3" />
        <path d="M10.2 10.2 14 14" stroke="currentColor" strokeWidth="1.3" fill="none" />
      </svg>
      <input
        className="rc-command-input"
        type="search"
        value={text}
        placeholder="Ticker or board"
        aria-label="Ticker or board"
        aria-controls={listId}
        onChange={(event) => setText(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter') submit();
        }}
      />
      {matches.length > 0 && (
        <ul className="rc-command-list" id={listId} role="listbox" aria-label="Boards">
          {matches.map((board) => (
            <li key={board.key}>
              <button type="button" className="rc-command-row" role="option" aria-selected="false" onClick={() => onPickBoard(board.key)}>
                {board.name}
                {board.group !== undefined && <span className="rc-command-group">{board.group}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export type AppBarProps = {
  /** our mark · the command box · the data-freshness dot · the clock (Amsterdam) · the account (contract §6). */
  command: ReactNode;
  freshness: { tone: 'pos' | 'amber' | 'neg'; label: string };
  nowMs: number;
  account: string;
};

/** `app-bar`. */
export function AppBar({ command, freshness, nowMs, account }: AppBarProps) {
  return (
    <header className="rc-appbar" data-rc="app-bar">
      <span className="rc-appbar-mark">RevenueChaser</span>
      <div className="rc-appbar-command">{command}</div>
      <span className="rc-freshness" data-rc="freshness" data-tone={freshness.tone} title={freshness.label}>
        <span className="rc-freshness-dot" aria-hidden="true" />
        <span className="rc-freshness-label">{freshness.label}</span>
      </span>
      <span className="rc-appbar-clock" data-rc="clock">
        {amsterdamTime(nowMs)} Amsterdam
      </span>
      <span className="rc-appbar-account">{account}</span>
    </header>
  );
}

export type BoardTabsProps = {
  boards: readonly BoardRef[];
  active: string;
  onSelect: (key: string) => void;
  /** 12 visible and the rest behind an overflow (contract §6). */
  visible?: number;
};

/** `board-tabs`: one filled block per board, the reference terminal's shape (contract §6). */
export function BoardTabs({ boards, active, onSelect, visible = 12 }: BoardTabsProps) {
  const shown = boards.slice(0, visible);
  const rest = boards.slice(visible);
  return (
    <nav className="rc-board-tabs" data-rc="board-tabs" aria-label="Boards">
      {shown.map((board) => (
        <button
          type="button"
          key={board.key}
          className="rc-board-tab"
          aria-current={board.key === active ? 'page' : undefined}
          onClick={() => onSelect(board.key)}
        >
          {board.name}
        </button>
      ))}
      {rest.length > 0 && <BoardMenu label={`+${rest.length}`} boards={rest} onSelect={onSelect} />}
    </nav>
  );
}

export type BoardMenuProps = {
  label: string;
  boards: readonly BoardRef[];
  onSelect: (key: string) => void;
};

/** `nav-group-sheet`: the web's overflow menu, counterpart of the phone's upward group sheet (contract §5.2). */
export function BoardMenu({ label, boards, onSelect }: BoardMenuProps) {
  return (
    <details className="rc-board-overflow" data-rc="nav-group-sheet">
      <summary className="rc-board-tab">{label}</summary>
      <ul className="rc-board-overflow-list" role="menu">
        {boards.map((board) => (
          <li key={board.key}>
            <button type="button" className="rc-board-overflow-row" role="menuitem" onClick={() => onSelect(board.key)}>
              {board.name}
            </button>
          </li>
        ))}
      </ul>
    </details>
  );
}

export type DocumentTab = { id: string; title: string };

export type DocumentTabsProps = {
  /** Kept, for sub-screens only: a ticker page opened from a board splits the view (contract §6). */
  tabs: readonly DocumentTab[];
  active: string;
  onSelect: (id: string) => void;
  onClose: (id: string) => void;
};

/** `document-tabs`. */
export function DocumentTabs({ tabs, active, onSelect, onClose }: DocumentTabsProps) {
  if (tabs.length === 0) return null;
  return (
    <div className="rc-doc-tabs" data-rc="document-tabs" role="tablist" aria-label="Open pages">
      {tabs.map((tab) => (
        <span className="rc-doc-tab" key={tab.id} data-active={tab.id === active}>
          <button type="button" className="rc-doc-tab-name" role="tab" aria-selected={tab.id === active} onClick={() => onSelect(tab.id)}>
            {tab.title}
          </button>
          <button type="button" className="rc-doc-tab-close" aria-label={`Close ${tab.title}`} onClick={() => onClose(tab.id)}>
            ×
          </button>
        </span>
      ))}
    </div>
  );
}

/** The screen toolbar's action order is fixed, and both surfaces keep it (contract §6). */
export const TOOLBAR_ACTIONS = ['LAYOUTS', 'COMPACT', 'REFRESH', 'ADD', 'SAVE', 'RESET'] as const;

export type ScreenToolbarProps = {
  /** name · state · item count · scope · then the actions, in `TOOLBAR_ACTIONS` order (contract §6). */
  name: string;
  state: string;
  count: number;
  scope: string;
  onAction: (action: (typeof TOOLBAR_ACTIONS)[number]) => void;
  /** Which actions are unavailable on this board, so the row keeps its order instead of losing a button. */
  disabled?: readonly string[];
};

/** `screen-toolbar`. */
export function ScreenToolbar({ name, state, count, scope, onAction, disabled = [] }: ScreenToolbarProps) {
  return (
    <div className="rc-toolbar" data-rc="screen-toolbar">
      <span className="rc-toolbar-name">{name}</span>
      <Badge kind="state" tone="sky">
        {state}
      </Badge>
      <span className="rc-toolbar-count">{count} items</span>
      <span className="rc-toolbar-scope">{scope}</span>
      <span className="rc-toolbar-spacer" />
      {TOOLBAR_ACTIONS.map((action) => (
        <button
          type="button"
          key={action}
          className="rc-button"
          disabled={disabled.includes(action)}
          onClick={() => onAction(action)}
        >
          {action}
        </button>
      ))}
    </div>
  );
}

export type StatusLineProps = {
  /** rows, the build or job that produced them, and the as-of (contract §6). */
  rows: number;
  build: string;
  asof: string;
  /** What is running, repeated here from a loading panel's strip (contract §8). */
  running?: string;
};

/** `status-bar`. */
export function StatusLine({ rows, build, asof, running }: StatusLineProps) {
  return (
    <footer className="rc-statusbar" data-rc="status-bar">
      <span>{rows.toLocaleString('en-US')} rows</span>
      <span>{build}</span>
      <span>as of {asof}</span>
      {running !== undefined && <span className="rc-statusbar-running">{running}</span>}
    </footer>
  );
}

export type DetailRailProps = {
  title: string;
  children: ReactNode;
  onClose: () => void;
};

/** `detail-rail`: a row opens it; the phone's counterpart is a modal bottom sheet (contract §9). */
export function DetailRail({ title, children, onClose }: DetailRailProps) {
  return (
    <aside className="rc-detail-rail" data-rc="detail-rail" aria-label={title}>
      <header className="rc-detail-head">
        <h2 className="rc-detail-title">{title}</h2>
        <button type="button" className="rc-icon-button" onClick={onClose} aria-label="Close">
          ×
        </button>
      </header>
      <div className="rc-detail-body">{children}</div>
    </aside>
  );
}

export type ShellProps = {
  boards: readonly BoardRef[];
  active: string;
  onSelectBoard: (key: string) => void;
  appBar: ReactNode;
  documentTabs?: ReactNode;
  toolbar?: ReactNode;
  statusBar: ReactNode;
  /** The one fixed rail per board: freshness, running jobs, today's alerts, next earnings, market hours (§6). */
  rail?: ReactNode;
  detail?: ReactNode;
  children: ReactNode;
  askBubble?: ReactNode;
};

/** `shell`: the rail/sidebar of contract §5.1 and the seven frame rows of §6, in that order. */
export function Shell({
  boards,
  active,
  onSelectBoard,
  appBar,
  documentTabs,
  toolbar,
  statusBar,
  rail,
  detail,
  children,
  askBubble,
}: ShellProps) {
  const main = useRef<HTMLDivElement | null>(null);
  return (
    <div className="rc-shell" data-rc="shell">
      {appBar}
      <div className="rc-shell-main">
        <nav className="rc-sidebar" data-rc="sidebar" aria-label="Board groups">
          {boards.map((board) => (
            <button
              type="button"
              key={board.key}
              className="rc-sidebar-item"
              title={board.name}
              aria-current={board.key === active ? 'page' : undefined}
              onClick={() => onSelectBoard(board.key)}
            >
              <span className="rc-sidebar-icon" aria-hidden="true">
                {board.name.slice(0, 1)}
              </span>
              <span className="rc-sidebar-name">{board.name}</span>
            </button>
          ))}
        </nav>
        <div className="rc-shell-screen">
          <BoardTabs boards={boards} active={active} onSelect={onSelectBoard} />
          {documentTabs}
          {toolbar}
          <div className="rc-work" data-rc="work-area" ref={main}>
            <div className="rc-work-panels">{children}</div>
            {rail !== undefined && (
              <aside className="rc-work-rail" data-rc="board-rail">
                {rail}
              </aside>
            )}
          </div>
        </div>
        {detail}
      </div>
      {statusBar}
      {askBubble}
    </div>
  );
}
