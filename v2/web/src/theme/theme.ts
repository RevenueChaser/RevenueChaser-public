/** The theme contract of claude-coordinator `ref/design-system/theme.js`, in TypeScript (ADR decision 5).
 *
 * Dark is the default and is stored as the absence of the key, so a fresh browser is dark without a write.
 * `light` and `auto` are stored; `auto` follows `prefers-color-scheme` through the token file's media query.
 */
export const THEME_KEY = 'rc-theme';

export type Theme = 'dark' | 'light' | 'auto';

/** The theme a stored value means. Anything but `light` or `auto` is dark, including a missing or broken store. */
export function themeOf(stored: string | null): Theme {
  return stored === 'light' || stored === 'auto' ? stored : 'dark';
}

function store(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null; // a private window, or site data blocked: dark, and nothing is remembered
  }
}

export function storedTheme(): Theme {
  try {
    return themeOf(store()?.getItem(THEME_KEY) ?? null);
  } catch {
    return 'dark';
  }
}

export function applyTheme(theme: Theme): Theme {
  document.documentElement.setAttribute('data-theme', theme);
  return theme;
}

/** Write the choice and apply it. Dark removes the key, as in the shared contract. */
export function setTheme(theme: Theme): Theme {
  try {
    if (theme === 'dark') store()?.removeItem(THEME_KEY);
    else store()?.setItem(THEME_KEY, theme);
  } catch {
    // the choice still applies for this page
  }
  return applyTheme(theme);
}

export function applyStoredTheme(): Theme {
  return applyTheme(storedTheme());
}
