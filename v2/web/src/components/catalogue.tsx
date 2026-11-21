/** `widget-catalogue`, `settings-rail` and `format-preview`: the three parts a board does not own.
 *
 * Contract §7 (every panel carries a one-sentence description and an honest scope, shown in the catalogue),
 * §3 (the formatting rules, judgeable only against a real string) and §9 (the settings rail's two groups).
 */
import { useMemo, useState } from 'react';

import { compact, currencyLabel, pct, price } from '../format/format';

export type WidgetEntry = {
  id: string;
  name: string;
  category: string;
  /** The sentence and the honest scope every panel carries (contract §7). */
  description: string;
  honestScope: string;
};

export type WidgetCatalogueProps = {
  entries: readonly WidgetEntry[];
  onAdd: (id: string) => void;
};

/** `widget-catalogue`: search · category chips · two-column cards, each with a sentence and a scope (§9). */
export function WidgetCatalogue({ entries, onAdd }: WidgetCatalogueProps) {
  const [text, setText] = useState('');
  const [category, setCategory] = useState<string | null>(null);
  const categories = useMemo(() => [...new Set(entries.map((entry) => entry.category))].sort(), [entries]);
  const shown = useMemo(() => {
    const needle = text.trim().toLowerCase();
    return entries.filter(
      (entry) =>
        (category === null || entry.category === category) &&
        (needle === '' || entry.name.toLowerCase().includes(needle) || entry.description.toLowerCase().includes(needle)),
    );
  }, [entries, text, category]);

  return (
    <div className="rc-catalogue" data-rc="widget-catalogue">
      <input
        className="rc-input"
        type="search"
        value={text}
        placeholder="Search widgets"
        aria-label="Search widgets"
        onChange={(event) => setText(event.target.value)}
      />
      <div className="rc-catalogue-categories">
        <button type="button" className="rc-chip" data-on={category === null} onClick={() => setCategory(null)}>
          All
        </button>
        {categories.map((name) => (
          <button
            type="button"
            key={name}
            className="rc-chip"
            data-on={category === name}
            onClick={() => setCategory(name)}
          >
            {name}
          </button>
        ))}
      </div>
      <div className="rc-catalogue-grid">
        {shown.map((entry) => (
          <article className="rc-catalogue-card" key={entry.id}>
            <h4 className="rc-catalogue-name">{entry.name}</h4>
            <p className="rc-catalogue-description">{entry.description}</p>
            <p className="rc-catalogue-honest">{entry.honestScope}</p>
            <button type="button" className="rc-button" onClick={() => onAdd(entry.id)}>
              ADD
            </button>
          </article>
        ))}
        {shown.length === 0 && <p className="rc-catalogue-empty">No widget matches that.</p>}
      </div>
    </div>
  );
}

export type SettingsGroup = { name: 'Shell' | 'Data'; items: ReadonlyArray<{ id: string; label: string }> };

export type SettingsRailProps = {
  groups: readonly SettingsGroup[];
  active: string;
  onSelect: (id: string) => void;
};

/** `settings-rail`: a search box above two groups, Shell and Data (contract §9). Step 9 fills the screens. */
export function SettingsRail({ groups, active, onSelect }: SettingsRailProps) {
  const [text, setText] = useState('');
  const needle = text.trim().toLowerCase();
  return (
    <nav className="rc-settings-rail" data-rc="settings-rail" aria-label="Settings">
      <input
        className="rc-input"
        type="search"
        value={text}
        placeholder="Search settings"
        aria-label="Search settings"
        onChange={(event) => setText(event.target.value)}
      />
      {groups.map((group) => {
        const items = group.items.filter((item) => needle === '' || item.label.toLowerCase().includes(needle));
        if (items.length === 0) return null;
        return (
          <div className="rc-settings-group" key={group.name}>
            <h3 className="rc-settings-group-name">{group.name}</h3>
            {items.map((item) => (
              <button
                type="button"
                key={item.id}
                className="rc-settings-item"
                aria-current={item.id === active ? 'page' : undefined}
                onClick={() => onSelect(item.id)}
              >
                {item.label}
              </button>
            ))}
          </div>
        );
      })}
    </nav>
  );
}

export type FormatRules = {
  currency: string;
  /** Another currency in the same view, which is what makes a code appear (contract §3). */
  alsoInView?: readonly string[];
  precision: number;
  /** The rate and its as-of, printed wherever a conversion happened (contract §3). */
  rate?: { value: number; asof: string };
};

/** `format-preview`: the live preview of contract §3 — a format rule is only judgeable against a real string. */
export function FormatPreview({ rules }: { rules: FormatRules }) {
  const label = currencyLabel(rules.currency, rules.alsoInView ?? []);
  const rows: Array<[string, string]> = [
    ['A price', price(184.236, label, rules.precision)],
    ['A small price', price(0.4821, label)],
    ['A total', compact(1_234_567_890, label)],
    ['A change', pct(-1.237, 2)],
    ['A missing value', '—'],
  ];
  return (
    <div className="rc-format-preview" data-rc="format-preview">
      <dl className="rc-format-rows">
        {rows.map(([name, value]) => (
          <div className="rc-format-row" key={name}>
            <dt>{name}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      {rules.rate !== undefined && (
        <p className="rc-format-rate">
          Converted at {rules.rate.value.toFixed(4)}, as of {rules.rate.asof}.
        </p>
      )}
    </div>
  );
}
