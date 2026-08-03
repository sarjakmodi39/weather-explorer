/** Owns the resolved theme, the `data-theme` stamp on <html>, and the
 *  localStorage persistence. Until the user toggles, the app tracks the OS
 *  preference live (so a system-theme change is picked up without reload);
 *  once toggled, the choice is stamped explicitly and wins in both directions
 *  over `prefers-color-scheme`, matching the CSS pattern in index.css. */

import { useCallback, useEffect, useState } from 'react'

import {
  CHART_COLORS,
  getStoredTheme,
  getSystemTheme,
  THEME_STORAGE_KEY,
  type Theme,
} from '../lib/theme'

export function useTheme() {
  const [explicit, setExplicit] = useState(() => getStoredTheme() !== null)
  const [theme, setTheme] = useState<Theme>(() => getStoredTheme() ?? getSystemTheme())

  useEffect(() => {
    const root = document.documentElement
    if (explicit) {
      root.setAttribute('data-theme', theme)
    } else {
      root.removeAttribute('data-theme')
    }
  }, [theme, explicit])

  // Follow OS changes live only while the user hasn't made an explicit choice.
  useEffect(() => {
    if (explicit || typeof window === 'undefined' || !window.matchMedia) return

    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const handleChange = (event: MediaQueryListEvent) => {
      setTheme(event.matches ? 'dark' : 'light')
    }
    media.addEventListener('change', handleChange)
    return () => media.removeEventListener('change', handleChange)
  }, [explicit])

  const toggleTheme = useCallback(() => {
    setTheme((current) => {
      const next: Theme = current === 'dark' ? 'light' : 'dark'
      window.localStorage.setItem(THEME_STORAGE_KEY, next)
      return next
    })
    setExplicit(true)
  }, [])

  return { theme, toggleTheme, colors: CHART_COLORS[theme] }
}
