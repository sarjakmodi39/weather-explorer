/** Theme tokens, kept in one place so the CSS custom properties in index.css
 *  and the JS-side colors handed to Recharts (which takes colors as props,
 *  not CSS) can never drift apart — this file is the single source for both.
 *  The four series hex values and the chart-chrome roles are the ones
 *  validated for colorblind safety; do not edit them here without also
 *  updating index.css, and vice versa. */

export type Theme = 'light' | 'dark'

export const THEME_STORAGE_KEY = 'weather-explorer-theme'

export interface ChartColors {
  surface: string
  page: string
  inkPrimary: string
  inkSecondary: string
  inkMuted: string
  gridline: string
  axis: string
  seriesMax: string
  seriesMin: string
  feelsMax: string
  feelsMin: string
}

export const CHART_COLORS: Record<Theme, ChartColors> = {
  light: {
    surface: '#fcfcfb',
    page: '#f9f9f7',
    inkPrimary: '#0b0b0b',
    inkSecondary: '#52514e',
    inkMuted: '#898781',
    gridline: '#e1e0d9',
    axis: '#c3c2b7',
    seriesMax: '#dc2626',
    seriesMin: '#2563eb',
    feelsMax: '#f97316',
    feelsMin: '#0891b2',
  },
  dark: {
    surface: '#1a1a19',
    page: '#0d0d0d',
    inkPrimary: '#ffffff',
    inkSecondary: '#c3c2b7',
    inkMuted: '#898781',
    gridline: '#2c2c2a',
    axis: '#383835',
    seriesMax: '#e66767',
    seriesMin: '#3987e5',
    feelsMax: '#d95926',
    feelsMin: '#0891b2',
  },
}

/** SSR-safe: this app has no server render, but keeping the guard costs
 *  nothing and makes the function safe to call from module scope or tests. */
export function getSystemTheme(): Theme {
  if (typeof window === 'undefined' || !window.matchMedia) return 'light'
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

/** Null means "no explicit choice yet" — the caller should keep following
 *  the OS preference rather than pin to a stamped value. */
export function getStoredTheme(): Theme | null {
  if (typeof window === 'undefined') return null
  const stored = window.localStorage.getItem(THEME_STORAGE_KEY)
  return stored === 'light' || stored === 'dark' ? stored : null
}
