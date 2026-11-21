/** The small parts every board reaches for, and the eight states that replace a panel body (contract §8).
 *
 * None of these decides a colour: a `Tone` names a token and the stylesheet resolves it.
 */
import type { ReactNode } from 'react';

import type { Tone } from '../board/envelope';
import { pct, signTone } from '../format/format';

export type ChipProps = { label: string; value?: string; tone?: Tone; title?: string };

/** `chip`: pill radius, and each chip its own fixed column in a row (contract §9, §11). */
export function Chip({ label, value, tone = 'neutral', title }: ChipProps) {
  return (
    <span className="rc-chip" data-tone={tone} data-rc="chip" title={title}>
      <span className="rc-chip-label">{label}</span>
      {value !== undefined && <span className="rc-chip-value">{value}</span>}
    </span>
  );
}

export type BadgeProps = { children: ReactNode; tone?: Tone; kind?: 'count' | 'state' };

/** `badge`: the count badge of a panel header and the state badge of a toolbar (contract §7, §9). */
export function Badge({ children, tone = 'neutral', kind = 'count' }: BadgeProps) {
  return (
    <span className="rc-badge" data-tone={tone} data-kind={kind} data-rc="badge">
      {children}
    </span>
  );
}

/** A delta chip: the signed percentage, coloured by its own sign and nothing else (contract §3). */
export function DeltaChip({ value, label }: { value: number | null; label?: string }) {
  return (
    <span className="rc-delta" data-tone={signTone(value)} data-rc="delta">
      {pct(value)}
      {label !== undefined && <span className="rc-delta-label">{label}</span>}
    </span>
  );
}

export type NoticeProps = {
  /** A plain sentence. Contract §8: no data, an upstream down, or a write refused — never a blank panel. */
  children: ReactNode;
  tone?: Tone;
  /** The probe result of an upstream that is down, or the reason a write was refused. */
  detail?: string;
};

/** `notice`: a class has no data, an upstream is down, a write is refused (contract §8). */
export function Notice({ children, tone = 'neutral', detail }: NoticeProps) {
  return (
    <div className="rc-notice" data-tone={tone} data-rc="notice" role="status">
      <p className="rc-notice-text">{children}</p>
      {detail !== undefined && <p className="rc-notice-detail">{detail}</p>}
    </div>
  );
}

export type BannerProps = {
  children: ReactNode;
  tone?: Tone;
  /** What the screen is waiting for, which a sample-data banner must say (contract §8). */
  waitingFor?: string;
};

/** `banner`: sample data, stale data, partial data — it admits it rather than looking live (contract §8, §12). */
export function Banner({ children, tone = 'amber', waitingFor }: BannerProps) {
  return (
    <div className="rc-banner" data-tone={tone} data-rc="banner" role="status">
      <span className="rc-banner-text">{children}</span>
      {waitingFor !== undefined && <span className="rc-banner-wait">Waiting for {waitingFor}.</span>}
    </div>
  );
}

export type SkeletonRowsProps = {
  /** The real column layout, so the skeleton is the table's own shape and not grey soup (contract §8). */
  widths: readonly string[];
  rows?: number;
  /** The strip naming what is running, repeated in the status bar. */
  running?: string;
  /** 0..1, or null for an indeterminate line. */
  progress?: number | null;
};

/** `skeleton`: a loading table, and a graph's missing sections as `Loading…` cards (contract §8). */
export function SkeletonRows({ widths, rows = 6, running, progress = null }: SkeletonRowsProps) {
  return (
    <div className="rc-skeleton" data-rc="skeleton" aria-busy="true">
      {running !== undefined && <div className="rc-skeleton-running">{running}</div>}
      <div className="rc-progress" data-indeterminate={progress === null}>
        <span className="rc-progress-fill" style={{ width: progress === null ? '100%' : `${Math.round(progress * 100)}%` }} />
      </div>
      {Array.from({ length: rows }, (_, row) => (
        <div className="rc-skeleton-row" key={row}>
          {widths.map((width, cell) => (
            <span className="rc-skeleton-cell" key={cell} style={{ width }} />
          ))}
        </div>
      ))}
    </div>
  );
}

export type NextStepCardProps = {
  /** What the thing is, and what the next step is — with that step as a button (contract §8). */
  title: string;
  what: string;
  action: string;
  onAction: () => void;
};

/** `next-step-card`: nothing configured (contract §8). */
export function NextStepCard({ title, what, action, onAction }: NextStepCardProps) {
  return (
    <div className="rc-next-step" data-rc="next-step-card">
      <h3 className="rc-next-step-title">{title}</h3>
      <p className="rc-next-step-what">{what}</p>
      <button type="button" className="rc-button" data-variant="primary" onClick={onAction}>
        {action}
      </button>
    </div>
  );
}

export type DialogProps = {
  title: string;
  children: ReactNode;
  /** The buttons, in the order they are offered. */
  actions: ReactNode;
  onDismiss?: () => void;
};

/** `dialog`: `--r-lg` and `--elev-2` (contract §4, §9). */
export function Dialog({ title, children, actions, onDismiss }: DialogProps) {
  return (
    <div className="rc-scrim" data-rc="scrim" onClick={onDismiss}>
      <div
        className="rc-dialog"
        data-rc="dialog"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(event) => event.stopPropagation()}
      >
        <h3 className="rc-dialog-title">{title}</h3>
        <div className="rc-dialog-body">{children}</div>
        <div className="rc-dialog-actions">{actions}</div>
      </div>
    </div>
  );
}

export type UnsavedDialogProps = {
  /** What is unsaved, named: a modal that only says "unsaved changes" is not this state (contract §8). */
  unsaved: readonly string[];
  onDiscard: () => void;
  onCancel: () => void;
};

/** `unsaved-dialog`: an edit is unsaved (contract §8). */
export function UnsavedDialog({ unsaved, onDiscard, onCancel }: UnsavedDialogProps) {
  return (
    <Dialog
      title="Unsaved changes"
      onDismiss={onCancel}
      actions={
        <>
          <button type="button" className="rc-button" onClick={onDiscard}>
            Discard
          </button>
          <button type="button" className="rc-button" data-variant="primary" onClick={onCancel}>
            Cancel
          </button>
        </>
      }
    >
      <p className="rc-dialog-text">These edits are not saved:</p>
      <ul className="rc-dialog-list" data-rc="unsaved-list">
        {unsaved.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </Dialog>
  );
}

export type EstimateGateProps = {
  /** The panel's own description, so a gated panel still says what it is (contract §8). */
  description: string;
  /** The price per call, in words. A gate without a price is not a gate. */
  pricePerCall: string;
  /** How many calls the load would make, where the panel knows. */
  calls?: number;
  onLoad: () => void;
};

/** `estimate-gate`: gated by cost or a long job; **it never fetches on its own** (contract §8, §12). */
export function EstimateGate({ description, pricePerCall, calls, onLoad }: EstimateGateProps) {
  return (
    <div className="rc-gate" data-rc="estimate-gate">
      <p className="rc-gate-text">{description}</p>
      <p className="rc-gate-price">
        {pricePerCall}
        {calls !== undefined && <span className="rc-gate-calls">{calls} calls</span>}
      </p>
      <button type="button" className="rc-button" data-variant="primary" onClick={onLoad}>
        LOAD
      </button>
      <p className="rc-gate-note">Nothing is fetched until you press LOAD.</p>
    </div>
  );
}

export type SegmentedControlProps = {
  options: readonly string[];
  selected: string;
  onSelect: (option: string) => void;
  label: string;
};

/** `segmented`: exclusive, and never a dropdown at five or fewer choices (contract §7). */
export function SegmentedControl({ options, selected, onSelect, label }: SegmentedControlProps) {
  return (
    <div className="rc-segmented" data-rc="segmented" role="group" aria-label={label}>
      {options.map((option) => (
        <button
          type="button"
          key={option}
          className="rc-segment"
          aria-pressed={option === selected}
          onClick={() => onSelect(option)}
        >
          {option}
        </button>
      ))}
    </div>
  );
}

/** `ask-bubble`: a floating round button, bottom right, on every screen (contract §6, §9). */
export function AskBubble({ onOpen }: { onOpen: () => void }) {
  return (
    <button type="button" className="rc-ask" data-rc="ask-bubble" onClick={onOpen} aria-label="Ask Claude">
      <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false">
        <path
          d="M2.5 3.5h11v7h-6l-3 2.5v-2.5h-2z"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.3"
          strokeLinejoin="round"
        />
      </svg>
    </button>
  );
}
