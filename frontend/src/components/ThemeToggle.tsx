import type { Theme } from '../lib/theme'

export function ThemeToggle({ theme, onToggle }: { theme: Theme; onToggle: () => void }) {
  const isDark = theme === 'dark'

  return (
    <button
      type="button"
      onClick={onToggle}
      aria-pressed={isDark}
      className="shrink-0 rounded-md border border-[var(--axis-line)] px-3 py-1.5 text-sm font-medium text-[var(--ink-secondary)] transition-colors hover:bg-[var(--surface-card)]"
    >
      {isDark ? 'Dark' : 'Light'} mode
    </button>
  )
}
