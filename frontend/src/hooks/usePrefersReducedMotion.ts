/** Tracks the `prefers-reduced-motion: reduce` media query live. CSS handles
 *  its own reduced-motion overrides (see index.css), but Recharts' built-in
 *  chart animation is driven by JS props (`isAnimationActive`), which CSS
 *  cannot reach — this hook is what lets the chart honor the same
 *  preference. */

import { useEffect, useState } from 'react'

const QUERY = '(prefers-reduced-motion: reduce)'

function getPrefersReducedMotion(): boolean {
  if (typeof window === 'undefined' || !window.matchMedia) return false
  return window.matchMedia(QUERY).matches
}

export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(getPrefersReducedMotion)

  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return

    const media = window.matchMedia(QUERY)
    const handleChange = (event: MediaQueryListEvent) => setReduced(event.matches)
    media.addEventListener('change', handleChange)
    return () => media.removeEventListener('change', handleChange)
  }, [])

  return reduced
}
