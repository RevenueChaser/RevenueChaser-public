/** `theme-switch`: dark / light / auto, the `rc-theme` contract of contract §2 — dark is the stored absence. */
import { useState } from 'react';

import { SegmentedControl } from './primitives';
import { setTheme, storedTheme, type Theme } from '../theme/theme';

const OPTIONS: Theme[] = ['dark', 'light', 'auto'];
const LABELS: Record<Theme, string> = { dark: 'Dark', light: 'Light', auto: 'Auto' };

export function ThemeSwitch() {
  const [theme, setCurrent] = useState<Theme>(() => storedTheme());
  return (
    <div className="rc-theme-switch" data-rc="theme-switch">
      <SegmentedControl
        label="Theme"
        options={OPTIONS.map((option) => LABELS[option])}
        selected={LABELS[theme]}
        onSelect={(label) => {
          const next = OPTIONS.find((option) => LABELS[option] === label) ?? 'dark';
          setCurrent(setTheme(next));
        }}
      />
    </div>
  );
}
