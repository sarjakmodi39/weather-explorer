import type { Theme } from '../lib/theme'

export function ThemeToggle({ theme, onToggle }: { theme: Theme; onToggle: () => void }) {
  const isDark = theme === 'dark'
  // A state label ("Light mode" while light) reads as the button's target,
  // not its current state — a light-mode reader would expect clicking it to
  // *give* them light mode. Label the action instead, so it can only be
  // read one way; aria-checked (via role="switch") carries the state for
  // assistive tech separately from that action text.
  const nextTheme = isDark ? 'light' : 'dark'

  return (
    <button
      type="button"
      onClick={onToggle}
      role="switch"
      aria-checked={isDark}
      aria-label={`Switch to ${nextTheme} mode`}
      className="btn-secondary shrink-0"
    >
      Switch to {nextTheme}
    </button>
  )
}
